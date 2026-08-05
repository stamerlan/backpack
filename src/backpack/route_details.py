import logging
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor

from . import model, route
from .overpass import Overpass

logger = logging.getLogger(__name__)

POI_SAMPLE_M = 350.0
POI_FILTERS = (
    '[natural~"peak|spring|saddle|cave_entrance|water"]',
    '[tourism~"viewpoint|alpine_hut|wilderness_hut'
    '|attraction|camp_site|picnic_site"]',
    '[amenity~"shelter|drinking_water|toilets|shower"]',
    '[mountain_pass=yes]',
    '[historic]',
)

class RouteDetails:
    """Loads route detail data off the mainloop, hiding the Overpass client. """

    def __init__(self) -> None:
        self._overpass = Overpass()
        # Two workers mirror Overpass's own slot budget; more would just block
        # on the server's rate limit anyway.
        self._pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="route-details"
        )

    def load_poi(
        self, track: tuple[model.TrackPoint, ...]
    ) -> "Future[tuple[model.Poi, ...]]":
        """Start loading POIs near track and return the pending future.

        The future resolves to the POIs found (an empty tuple when none), or
        fails with CancelledError if the service is cancelled while it runs.
        """
        return self._pool.submit(self._fetch_poi, track)

    def cancel(self) -> None:
        """Abort in-flight loads and stop accepting new ones.

        Thread safe, so it may be called from the shutdown handler. Aborting
        Overpass makes each running load raise CancelledError and finish;
        queued loads are dropped.
        """
        self._overpass.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _fetch_poi(
        self, track: tuple[model.TrackPoint, ...]
    ) -> tuple[model.Poi, ...]:
        """Query Overpass for POIs near the track. Runs on a worker thread.

        Sampled every POI_SAMPLE_M along the track, searched within a slightly
        larger radius to find all POI within POI_SAMPLE_M from any point on
        track.
        """
        sampled_track = route.sample(track, POI_SAMPLE_M)
        if not sampled_track:
            return ()
        try:
            around = ",".join(f"{lat},{lon}" for lat, lon in sampled_track)
            body = "\n".join(
                f"  nwr(around:{POI_SAMPLE_M * 1.118},{around}){f};"
                for f in POI_FILTERS
            )
            query = f"[out:json][timeout:180];\n(\n{body}\n);\nout center;\n"
            result = self._overpass.query(query)
        except Overpass.Aborted:
            raise CancelledError from None      # unwind quietly on shutdown

        found: list[tuple[float, model.Poi]] = []

        def add(lat: float, lon: float, tags: dict[str, str]) -> None:
            if not tags:                    # bare geometry, nothing to describe
                return
            near = route.nearest(lat, lon, track)
            found.append((
                near.dist_m,
                model.Poi(
                    lat=lat, long=lon,
                    ofs_m=route.distance_m((lat, lon), near),
                    tags=dict(tags)
                )
            ))

        for node in result.nodes:
            add(float(node.lat), float(node.lon), node.tags)
        for way in result.ways:
            if way.center_lat is not None and way.center_lon is not None:
                add(float(way.center_lat), float(way.center_lon), way.tags)
        for rel in result.relations:
            if rel.center_lat is not None and rel.center_lon is not None:
                add(float(rel.center_lat), float(rel.center_lon), rel.tags)

        found.sort(key=lambda p: p[0])      # nearest the start first
        return tuple(p[1] for p in found)
