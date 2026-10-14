#include "dialog.h"
#include <wrl/client.h>
#include <shobjidl.h>
#include "logger.h"
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

static std::expected<ComPtr<IFileDialog>, HRESULT>
new_dialog(REFCLSID clsid, FILEOPENDIALOGOPTIONS extra,
	const dialog::filters_t& filters) noexcept
{
	ComPtr<IFileDialog> dlg;
	HRESULT hr = CoCreateInstance(clsid, nullptr, CLSCTX_INPROC_SERVER,
		IID_PPV_ARGS(&dlg));
	if (FAILED(hr)) {
		logger::error("create dialog failed: {}", fmt_err(hr));
		return std::unexpected(hr);
	}

	FILEOPENDIALOGOPTIONS fos;
	dlg->GetOptions(&fos);
	dlg->SetOptions(fos | FOS_FORCEFILESYSTEM | FOS_NOCHANGEDIR | extra);

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
	return dlg;
}

static dialog::result_t show(IFileDialog *dlg, HWND owner) noexcept
{
	std::vector<std::wstring> paths;

	HRESULT hr = dlg->Show(owner);
	if (FAILED(hr)) {
		if (hr != HRESULT_FROM_WIN32(ERROR_CANCELLED))
			logger::error("show dialog failed: {}", fmt_err(hr));
		return std::unexpected(hr);
	}

	FILEOPENDIALOGOPTIONS fos = 0;
	dlg->GetOptions(&fos);
	if (fos & FOS_ALLOWMULTISELECT) {
		ComPtr<IFileOpenDialog> open;
		hr = dlg->QueryInterface(IID_PPV_ARGS(&open));

		ComPtr<IShellItemArray> items;
		if (SUCCEEDED(hr))
			hr = open->GetResults(&items);

		DWORD count = 0;
		if (SUCCEEDED(hr))
			hr = items->GetCount(&count);

		/* an unreadable item is skipped, the rest are still returned */
		for (DWORD i = 0; SUCCEEDED(hr) && i < count; ++i) {
			ComPtr<IShellItem> item;
			std::wstring path;
			HRESULT item_hr = items->GetItemAt(i, &item);
			if (SUCCEEDED(item_hr))
				item_hr = item_to_path(item.Get(), path);
			if (SUCCEEDED(item_hr))
				paths.push_back(std::move(path));
			else
				logger::warning("skip selected item {}: {}", i,
					fmt_err(item_hr));
		}
	} else {
		ComPtr<IShellItem> item;
		std::wstring path;
		hr = dlg->GetResult(&item);
		if (SUCCEEDED(hr))
			hr = item_to_path(item.Get(), path);
		if (SUCCEEDED(hr))
			paths.push_back(std::move(path));
	}

	if (FAILED(hr)) {
		logger::error("get result failed: {}", fmt_err(hr));
		return std::unexpected(hr);
	}
	return paths;
}

dialog::show_t dialog::open(bool select_multiple, filters_t filters)
{
	return [select_multiple, filters = std::move(filters)](HWND owner)
		noexcept -> result_t
	{
		auto dlg = new_dialog(CLSID_FileOpenDialog,
			select_multiple ? FOS_ALLOWMULTISELECT : 0, filters);
		if (!dlg)
			return std::unexpected(dlg.error());
		return show(dlg->Get(), owner);
	};
}

dialog::show_t dialog::save(std::wstring filename, filters_t filters)
{
	return [filename = std::move(filename), filters = std::move(filters)]
		(HWND owner) noexcept -> result_t
	{
		auto dlg = new_dialog(CLSID_FileSaveDialog, FOS_OVERWRITEPROMPT,
			filters);
		if (!dlg)
			return std::unexpected(dlg.error());
		if (!filename.empty())
			(*dlg)->SetFileName(filename.c_str());
		return show(dlg->Get(), owner);
	};
}
