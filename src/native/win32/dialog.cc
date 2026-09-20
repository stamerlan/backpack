#include "dialog.h"
#include <wrl/client.h>
#include <shobjidl.h>
#include "winerr.h"

#pragma comment(lib, "ole32.lib")

using Microsoft::WRL::ComPtr;

static HRESULT item_to_path(IShellItem *item, std::wstring& out)
{
	PWSTR psz = nullptr;
	HRESULT hr = item->GetDisplayName(SIGDN_FILESYSPATH, &psz);
	if (SUCCEEDED(hr) && psz)
		out.assign(psz);
	if (psz)
		CoTaskMemFree(psz);
	return hr;
}

dialog_t dialog_t::open_dialog(bool select_multiple,
	std::vector<std::pair<std::wstring, std::wstring>> filters)
{
	ComPtr<IFileDialog> dlg;

	HRESULT hr = CoCreateInstance(CLSID_FileOpenDialog, nullptr,
		CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dlg));
	if (FAILED(hr))
		throw com_error(hr,
			"CoCreateInstance(CLSID_FileOpenDialog) failed");

	dialog_t d{
		.dlg = dlg,
		.filters = std::move(filters),
		.allow_multi_select = select_multiple
	};

	FILEOPENDIALOGOPTIONS fos;
	dlg->GetOptions(&fos);
	fos |= FOS_FORCEFILESYSTEM | FOS_NOCHANGEDIR;
	if (select_multiple)
		fos |= FOS_ALLOWMULTISELECT;
	dlg->SetOptions(fos);

	return d;
}

dialog_t dialog_t::save_dialog(std::wstring filename,
	std::vector<std::pair<std::wstring, std::wstring>> filters)
{
	ComPtr<IFileDialog> dlg;

	HRESULT hr = CoCreateInstance(CLSID_FileSaveDialog, nullptr,
		CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dlg));
	if (FAILED(hr))
		throw com_error(hr,
			"CoCreateInstance(CLSID_FileSaveDialog) failed");

	dialog_t d{
		.dlg = dlg,
		.filters = std::move(filters),
		.allow_multi_select = false
	};

	FILEOPENDIALOGOPTIONS fos;
	dlg->GetOptions(&fos);
	fos |= FOS_FORCEFILESYSTEM | FOS_NOCHANGEDIR | FOS_OVERWRITEPROMPT;
	dlg->SetOptions(fos);

	if (!filename.empty())
		dlg->SetFileName(filename.c_str());

	return d;
}


dialog_t::result_t dialog_t::show(HWND owner) noexcept
{
	result_t result;

	/* COMDLG_FILTERSPEC points into the filter strings, so they must
	 * outlive Show; the filters member keeps them alive.
	 */
	std::vector<COMDLG_FILTERSPEC> filter_spec;
	filter_spec.reserve(filters.size());
	for (const auto& f : filters)
		filter_spec.push_back({ f.first.c_str(), f.second.c_str() });
	if (!filter_spec.empty()) {
		dlg->SetFileTypes(
			static_cast<UINT>(filter_spec.size()),
			filter_spec.data()
		);
	}

	HRESULT hr = dlg->Show(owner);
	if (FAILED(hr)) {
		if (hr == HRESULT_FROM_WIN32(ERROR_CANCELLED))
			result.cancelled = true;
		else
			result.hresult = hr;
		return result;
	}

	if (allow_multi_select) {
		ComPtr<IFileOpenDialog> open;
		hr = dlg.As(&open);

		ComPtr<IShellItemArray> items;
		if (SUCCEEDED(hr))
			hr = open->GetResults(&items);

		DWORD count = 0;
		if (SUCCEEDED(hr))
			hr = items->GetCount(&count);

		for (DWORD i = 0; SUCCEEDED(hr) && i < count; ++i) {
			ComPtr<IShellItem> item;
			if (FAILED(items->GetItemAt(i, &item)))
				continue;
			std::wstring path;
			if (SUCCEEDED(item_to_path(item.Get(), path)))
				result.paths.push_back(std::move(path));
		}
	} else {
		ComPtr<IShellItem> item;
		hr = dlg->GetResult(&item);
		if (SUCCEEDED(hr)) {
			std::wstring path;
			if (SUCCEEDED(item_to_path(item.Get(), path)))
				result.paths.push_back(std::move(path));
		}
	}

	if (FAILED(hr))
		result.hresult = hr;
	return result;
}
