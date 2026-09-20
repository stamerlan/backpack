#ifndef DIALOG_H
#define DIALOG_H

#include <vector>
#include <string>
#include <utility>

#include <shobjidl.h>
#include <windows.h>
#include <wrl/client.h>

struct dialog_t {
	struct result_t {
		HRESULT hresult = S_OK;
		bool cancelled = false;
		std::vector<std::wstring> paths;
	};

	static dialog_t open_dialog(bool select_multiple,
		std::vector<std::pair<std::wstring, std::wstring>> filters);
	static dialog_t save_dialog(std::wstring filename,
		std::vector<std::pair<std::wstring, std::wstring>> filters);

	result_t show(HWND owner) noexcept;

	Microsoft::WRL::ComPtr<IFileDialog> dlg;

	/* COMDLG_FILTERSPEC points into the filter strings, so they must have
	 * the same lifetime as this object.
	 */
	std::vector<std::pair<std::wstring, std::wstring>> filters;

	/* Set if open file dialog may select multiple items */
	bool allow_multi_select = false;
};

#endif /* DIALOG_H */
