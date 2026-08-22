"""
Open Privacy Filter GUI — Flet Edition

A cross-platform desktop front-end for the OpenAI Privacy Filter (OPF),
built with Flet (https://flet.dev) instead of tkinter.

Features:
    * Open, paste, edit, redact, copy, and save text
    * Automatically selects GPU (CUDA) or CPU
    * Windows, macOS, and Linux compatible
    * Falls back to web-browser mode if the native desktop client
      cannot be launched (e.g. blocked by Group Policy / AppLocker)

Version: 0.0.2
License: Apache 2.0
"""

import os
import asyncio
import traceback

#
# Dependency checks
#
try:
    import flet as ft
except ImportError:
    raise SystemExit(
        "Missing dependency: flet\n\n"
        "Install with:\n"
        "pip install flet"
    )

try:
    from opf import OPF
except ImportError:
    raise SystemExit(
        "Missing dependency: OpenAI Privacy Filter\n\n"
        "Install with:\n"
        "git clone https://github.com/openai/privacy-filter.git\n"
        "cd privacy-filter\n"
        "pip install -e ."
    )

try:
    import torch
except ImportError:
    raise SystemExit(
        "Missing dependency: torch\n\n"
        "Install with:\n"
        "pip install torch"
    )


class OPFGui:

    def __init__(self, page: ft.Page):

        self.page = page
        self.loop = asyncio.get_event_loop()
        self.opf = None
        self.model_loaded = False
        self.device = "unknown"
        self.last_directory = os.path.expanduser("~")
        self.file_picker = ft.FilePicker()
        self.save_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()
        self.build_ui()

    #################################################################
    # UI
    #################################################################

    def build_ui(self):

        self.page.title = "Open Privacy Filter GUI"
        self.page.window.width = 1400
        self.page.window.height = 800
        self.page.window.min_width = 900
        self.page.window.min_height = 560

        #
        # Toolbar
        #
        self.open_button = ft.OutlinedButton(
            "Open File",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self.open_file,
            key="open_button",
        )

        self.redact_button = ft.OutlinedButton(
            "Redact",
            icon=ft.Icons.SHIELD,
            on_click=self.start_redaction,
            key="redact_button",
        )

        self.paste_button = ft.OutlinedButton(
            "Paste",
            icon=ft.Icons.PASTE,
            on_click=self.paste_input,
            key="paste_button",
        )

        self.clear_button = ft.OutlinedButton(
            "Clear",
            icon=ft.Icons.DELETE_OUTLINE,
            on_click=self.clear_all,
            key="clear_button",
        )

        self.copy_button = ft.OutlinedButton(
            "Copy Output",
            icon=ft.Icons.COPY,
            on_click=self.copy_output,
            key="copy_button",
        )

        self.save_button = ft.OutlinedButton(
            "Save Output",
            icon=ft.Icons.SAVE_ALT,
            on_click=self.save_output,
            key="save_button",
        )

        self.about_button = ft.OutlinedButton(
            "About",
            icon=ft.Icons.INFO_OUTLINE,
            on_click=self.show_about,
            key="about_button",
        )

        self.progress_bar = ft.ProgressBar(
            value=None,
            width=200,
            visible=False,
            key="progress_bar",
        )

        self.toolbar_buttons = [
            self.open_button,
            self.paste_button,
            self.redact_button,
            self.clear_button,
            self.copy_button,
            self.save_button,
            self.about_button,
        ]

        toolbar = ft.Row(
            controls=[
                *self.toolbar_buttons,
                ft.Container(expand=True, key="toolbar_spacer"),
                self.progress_bar,
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            key="toolbar_row",
        )

        #
        # Input / output panels
        #
        self.input_field = ft.TextField(
            multiline=True,
            min_lines=1,
            expand=True,
            key="input_field",
        )

        self.output_field = ft.TextField(
            multiline=True,
            min_lines=1,
            expand=True,
            read_only=True,
            key="output_field",
        )

        input_panel = self.make_panel(
            "Input Text", self.input_field, panel_key="input_panel"
        )
        self.output_field_wrapper = ft.Container(
            content=self.output_field,
            expand=True,
            key="output_field_wrapper",
        )
        output_panel = self.make_panel_from_wrapper(
            "Redacted Output",
            self.output_field_wrapper,
            panel_key="output_panel",
        )

        main_row = ft.Row(
            controls=[
                input_panel,
                output_panel,
            ],
            expand=True,
            spacing=10,
            key="main_row",
        )

        #
        # Status bar
        #
        self.status_bar = ft.Text("Ready", color=ft.Colors.BLACK, key="status_text")

        status = ft.Container(
            content=self.status_bar,
            padding=ft.Padding(left=10, top=4, right=10, bottom=4),
            bgcolor=ft.Colors.GREY_200,
            border=ft.border.Border(
                top=ft.BorderSide(1, ft.Colors.GREY_300),
                right=ft.BorderSide(1, ft.Colors.GREY_300),
                bottom=ft.BorderSide(1, ft.Colors.GREY_300),
                left=ft.BorderSide(1, ft.Colors.GREY_300),
            ),
            border_radius=6,
            key="status_container",
        )

        self.page.add(
            ft.Column(
                controls=[
                    toolbar,
                    main_row,
                    status,
                ],
                expand=True,
                spacing=10,
                tight=True,
                key="root_column",
            )
        )

    def make_panel_from_wrapper(
        self, title: str, field_wrapper: ft.Container, panel_key: str
    ) -> ft.Container:
        """Same as make_panel(), but takes an already-built wrapper
        Container (instead of building one around `field` itself) so the
        caller can keep a reference to that wrapper and swap its
        .content later without touching the field control directly."""

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        title,
                        weight=ft.FontWeight.BOLD,
                        size=14,
                        key=f"{panel_key}_title",
                    ),
                    field_wrapper,
                ],
                expand=True,
                spacing=6,
                tight=True,
                key=f"{panel_key}_column",
            ),
            expand=True,
            padding=10,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.BLACK),
            border=ft.border.Border(
                top=ft.BorderSide(1, ft.Colors.GREY_300),
                right=ft.BorderSide(1, ft.Colors.GREY_300),
                bottom=ft.BorderSide(1, ft.Colors.GREY_300),
                left=ft.BorderSide(1, ft.Colors.GREY_300),
            ),
            border_radius=8,
            key=panel_key,
        )

    def replace_output_field(self, new_value: str):
        """Update the existing output TextField in place.

        The FrozenInstanceError is actually triggered when a brand new
        TextField is inserted into an already-mounted control tree and
        Flet tries to re-parent the new dataclass-backed control.
        Updating the existing control value avoids that reconciliation
        path entirely.
        """

        self.output_field.value = new_value
        self.output_field.update()

    def make_panel(
        self, title: str, field: ft.Control, panel_key: str
    ) -> ft.Container:

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        title,
                        weight=ft.FontWeight.BOLD,
                        size=14,
                        key=f"{panel_key}_title",
                    ),
                    ft.Container(
                        content=field,
                        expand=True,
                        key=f"{panel_key}_field_container",
                    ),
                ],
                expand=True,
                spacing=6,
                tight=True,
                key=f"{panel_key}_column",
            ),
            expand=True,
            padding=10,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.BLACK),
            border=ft.border.Border(
                top=ft.BorderSide(1, ft.Colors.GREY_300),
                right=ft.BorderSide(1, ft.Colors.GREY_300),
                bottom=ft.BorderSide(1, ft.Colors.GREY_300),
                left=ft.BorderSide(1, ft.Colors.GREY_300),
            ),
            border_radius=8,
            key=panel_key,
        )

    #################################################################
    # Status
    #################################################################
    
    def set_status(self, text: str):
        """Event-loop-thread only. Do not call from a worker thread."""
        self.status_bar.value = text
        self.status_bar.update()

    def set_status_threadsafe(self, text: str):
        """Safe to call from any thread — marshals the update to the event loop."""
        self.loop.call_soon_threadsafe(self.set_status, text)

    #################################################################
    # Dialogs
    #################################################################
    
    def show_dialog(self, dialog: ft.AlertDialog):
        self.page.show_dialog(dialog)

    def dismiss_dialog(self, _event=None):
        self.page.pop_dialog()

    def show_info_dialog(self, title: str, message: str):

        self.show_dialog(
            ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Text(message),
                actions=[
                    ft.TextButton(
                        "OK",
                        on_click=self.dismiss_dialog,
                    )
                ],
            )
        )

    def show_error_dialog(self, title: str, message: str):

        self.show_dialog(
            ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Column(
                    controls=[
                        ft.Text(
                            message,
                            selectable=True,
                        )
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    height=400,
                    tight=True,
                ),
                actions=[
                    ft.TextButton(
                        "OK",
                        on_click=self.dismiss_dialog,
                    )
                ],
            )
        )

    def show_about(self, e=None):

        self.show_info_dialog(
            "About",
            "Open Privacy Filter GUI\n"
            "Flet Edition — v0.0.2\n\n"
            "• Cross-platform desktop front-end for the OpenAI Privacy Filter.\n"
            "• License: Apache 2.0\n"
            "• Website: https://github.com/uwsph/opflet",
        )

    #################################################################
    # File open
    #################################################################
    
    async def open_file(self, e=None):

        files = await self.file_picker.pick_files(
            dialog_title="Open Text File",
            initial_directory=self.last_directory,
            allow_multiple=False,
            with_data=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt", "md", "csv", "log"],
        )

        if not files:
            self.set_status("Open cancelled")
            return

        picked = files[0]

        try:
            if picked.bytes is not None:
                content = picked.bytes.decode("utf-8", errors="replace")
            elif picked.path:
                with open(picked.path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            else:
                raise ValueError("No file data or path available.")

            self.input_field.value = content
            self.input_field.update()

            if picked.path:
                self.last_directory = os.path.dirname(picked.path)

            self.set_status(f"Loaded: {picked.name}")

        except Exception:
            self.show_error_dialog("Error Opening File", traceback.format_exc())
            self.set_status("Failed to open file")

    #################################################################
    # Save
    #################################################################
    
    async def save_output(self, e=None):

        if not self.output_field.value:
            self.set_status("Nothing to save")
            return

        path = await self.save_picker.save_file(
            dialog_title="Save Redacted Output",
            file_name="redacted_output.txt",
            initial_directory=self.last_directory,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"],
            src_bytes=self.output_field.value.encode("utf-8"),
        )

        if not path:
            self.set_status("Save cancelled")
            return

        self.last_directory = os.path.dirname(path)
        self.set_status(f"Saved: {os.path.basename(path)}")

    #################################################################
    # Clipboard
    #################################################################

    async def paste_input(self, e=None):
        text = await self.clipboard.get()
        if text:
            self.input_field.value = text
            self.input_field.update()
            self.set_status("Pasted from clipboard")
        else:
            self.set_status("Clipboard is empty")

    async def copy_output(self, e=None):
        if not self.output_field.value:
            self.set_status("Nothing to copy")
            return
        await self.clipboard.set(value=self.output_field.value)
        self.set_status("Copied to clipboard")

    #################################################################
    # Clear
    #################################################################

    def clear_all(self, e=None):
        self.input_field.value = ""
        self.input_field.update()
        self.replace_output_field("")
        self.set_status("Cleared")

    #################################################################
    # Redaction
    #################################################################
    
    async def start_redaction(self, e=None):

        source_text = self.input_field.value or ""

        if not source_text.strip():
            self.set_status("Nothing to redact")
            return

        self.progress_bar.visible = True
        self.redact_button.disabled = True
        self.progress_bar.update()
        self.redact_button.update()

        try:
            result = await self.loop.run_in_executor(
                None, self._redaction_blocking, source_text
            )
            self.replace_output_field(result)
            self.set_status("Redaction complete")

        except Exception:
            self.show_error_dialog("Redaction Error", traceback.format_exc())
            self.set_status("Redaction failed")

        finally:
            self.progress_bar.visible = False
            self.redact_button.disabled = False
            self.progress_bar.update()
            self.redact_button.update()

    def _redaction_blocking(self, source_text: str) -> str:
        """
        Runs on a worker thread via loop.run_in_executor(). Must NOT touch
        self.page / self.status_bar / any Flet control directly — use
        self.set_status_threadsafe() for progress updates instead.
        """
        self.load_model_if_needed()

        self.set_status_threadsafe(
            f"Redacting ({self.device.upper()})..."
        )

        result = self.opf.redact(source_text)

        return getattr(
            result,
            "redacted_text",
            str(result),
        )

    def load_model_if_needed(self):
        """
        May run on a worker thread (called from _redaction_blocking) —
        uses set_status_threadsafe(), never set_status(), for that reason.
        """
        if self.model_loaded:
            return

        self.set_status_threadsafe(
            "Loading model. First launch may download model files..."
        )

        try:

            if torch.cuda.is_available():

                #
                # Verify CUDA actually works
                #
                torch.tensor([1.0]).cuda()

                self.device = "cuda"

                gpu_name = torch.cuda.get_device_name(0)

                self.set_status_threadsafe(
                    f"Loading OPF on GPU: {gpu_name}"
                )

            else:

                self.device = "cpu"

                self.set_status_threadsafe(
                    "Loading OPF on CPU"
                )

        except Exception:

            self.device = "cpu"

            self.set_status_threadsafe(
                "GPU unavailable. Using CPU."
            )

        self.opf = OPF(
            device=self.device,
            output_mode="redacted",
        )

        self.model_loaded = True
        self.set_status_threadsafe(f"Model loaded on {self.device}")


def main(page: ft.Page):
    OPFGui(page)
    page.on_disappear = _on_window_close


def _on_window_close(page: ft.Page):
    """
    Called when the user closes the app window.
    Gives the Flutter engine a moment to clean up properly before
    the process exits, which prevents the Linux-specific warnings:

        embedder.cc (2603): 'FlutterEngineRemoveView' returned 'kInvalidArguments'
        Attempted to set message handler on an FlBinaryMessenger without an engine
    """
    try:
        page.close()
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    import os

    #
    # Option 1 — Fallback: suppress the specific warnings at the source.
    # These are harmless; we only care about them because they're noisy.
    #
    if sys.platform == "linux":
        import warnings

        _linux_state = {"suppressed": False}

        def _warning_filter(message, category, filename, lineno, file=None, line=None):
            if _linux_state["suppressed"]:
                return True
            text = str(message)
            if "FlutterEngineRemoveView" in text:
                _linux_state["suppressed"] = True
                return True
            if "FlBinaryMessenger" in text:
                _linux_state["suppressed"] = True
                return True
            return False

        warnings.showwarning = _warning_filter

        #
        # The Flutter engine and GLib emit warnings directly to stderr
        # (not via Python's warnings module), so we also filter stderr.
        #
        _original_stderr = sys.stderr

        class _FilteredStderr:
            """Wraps sys.stderr and filters out known harmless Linux warnings."""

            def __init__(self, wrapped):
                self._wrapped = wrapped
                self._suppressed = False

            def write(self, text):
                if self._suppressed:
                    return
                if "FlutterEngineRemoveView" in text:
                    self._suppressed = True
                    return
                if "FlBinaryMessenger" in text:
                    self._suppressed = True
                    return
                self._wrapped.write(text)

            def flush(self):
                self._wrapped.flush()

            def isatty(self):
                return self._wrapped.isatty()

        sys.stderr = _FilteredStderr(_original_stderr)

        #
        # GLib's g_warning writes directly to the stderr file descriptor (fd 2),
        # bypassing Python's sys.stderr wrapper. We redirect fd 2 to a pipe,
        # then run a background thread that reads from the pipe and filters
        # the output before writing to the original fd 2.
        #
        _original_fd2 = os.dup(2)
        _pipe_read, _pipe_write = os.pipe()

        class _Fd2Writer:
            """Write to the original fd 2."""
            def write(self, text):
                try:
                    os.write(_original_fd2, text.encode("utf-8", errors="replace"))
                except Exception:
                    pass
            def flush(self):
                pass
            def isatty(self):
                return os.isatty(_original_fd2)

        _fd2_output = _Fd2Writer()
        _fd2_state = {"suppressed": False}

        def _fd2_filter_loop():
            try:
                buf = b""
                while True:
                    chunk = os.read(_pipe_read, 4096)
                    if not chunk:
                        break
                    buf += chunk
                    for line in buf.split(b"\n"):
                        text = line.decode("utf-8", errors="replace")
                        if _fd2_state["suppressed"]:
                            continue
                        if "FlutterEngineRemoveView" in text:
                            _fd2_state["suppressed"] = True
                            continue
                        if "FlBinaryMessenger" in text:
                            _fd2_state["suppressed"] = True
                            continue
                        if "Gdk-Message" in text and "cursor theme" in text:
                            _fd2_state["suppressed"] = True
                            continue
                        if "Gtk-Message" in text and "Failed to load module" in text:
                            _fd2_state["suppressed"] = True
                            continue
                        _fd2_output.write(text + "\n")
                    buf = b""
            except Exception:
                pass

        import threading
        _fd2_thread = threading.Thread(target=_fd2_filter_loop, daemon=True)
        _fd2_thread.start()

        # Replace fd 2 with the write end of the pipe
        os.dup2(_pipe_write, 2)
        os.close(_pipe_write)

    def _launch(view=None):
        if hasattr(ft, "run"):
            if view is not None:
                ft.run(main, view=view)
            else:
                ft.run(main)
        else:
            if view is not None:
                ft.app(main, view=view)
            else:
                ft.app(main)

    try:
        _launch()
    except OSError as exc:
        print(f"Desktop launch failed ({exc}); falling back to web browser mode...")
        _launch(ft.AppView.WEB_BROWSER)
