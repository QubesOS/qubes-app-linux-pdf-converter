import os

from gi.repository import Nautilus, GObject, GLib


SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.odt', '.xlsx', '.ods')


class ConvertPdfItemExtension(GObject.GObject, Nautilus.MenuProvider):
    '''Send files to disposable virtual machine to convert to a safe format.

    Uses the nautilus-python api to provide a context menu within Nautilus which
    will enable the user to select file(s) to send to a disposable virtual
    machine for safe processing
    '''

    def get_file_items(self, *args):
        '''Attaches context menu in Nautilus to local file objects only.

        `args` will be `[files: List[Nautilus.FileInfo]]` in Nautilus 4.0 API,
        and `[window: Gtk.Widget, files: List[Nautilus.FileInfo]]` in Nautilus 3.0 API.
        '''
        files = args[-1]
        if not files:
            return

        for file_obj in files:

            # local files only; not remote
            if file_obj.get_uri_scheme() != 'file':
                return

            # Allow directories (they will be expanded by qvm-convert-pdf)
            if file_obj.is_directory():
                continue

            # Only attach context menu to supported file types
            _, ext = os.path.splitext(file_obj.get_name())
            if ext.lower() not in SUPPORTED_EXTENSIONS:
                return

        menu_item = Nautilus.MenuItem(name='QubesMenuProvider::ConvertPdf',
                                      label='Convert To Trusted PDF',
                                      tip='',
                                      icon='')

        menu_item.connect('activate', self.on_menu_item_clicked, files)
        return menu_item,

    def on_menu_item_clicked(self, menu, files):
        '''Called when user chooses files through Nautilus context menu.

        Collects all selected files and directories into a single
        qvm-convert-pdf.gnome invocation so one progress window is shown.
        '''
        paths = []
        backend = '--pdf'
        for file_obj in files:
            if file_obj.is_gone():
                continue
            if not file_obj.is_directory():
                _, ext = os.path.splitext(file_obj.get_name())
                if ext.lower() != '.pdf':
                    backend = '--file'
            paths.append(file_obj.get_location().get_path())

        if not paths:
            return

        cmd = ['/usr/lib/qubes/qvm-convert-pdf.gnome', backend] + paths
        pid = GLib.spawn_async(cmd)[0]
        GLib.spawn_close_pid(pid)
