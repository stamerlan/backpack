/* Inline SVG sprite reference shared across the UI. Icons live under
 * public/icons and expose a symbol with id "icon".
 */
export function icon(name: string, size = 20) {
  return (
    <svg width={size} height={size} aria-hidden="true">
      <use href={`icons/${name}.svg#icon`} />
    </svg>
  );
}
