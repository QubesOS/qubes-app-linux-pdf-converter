import os

from gi.repository import Nautilus, GObject, GLib


class ConvertPdfItemExtension(GObject.GObject, Nautilus.MenuProvider):
    '''Send PDF to disposable virtual machine to convert to a safe format.

    Uses the nautilus-python api to provide a context menu within Nautilus which
    will enable the user to select PDF file(s) to send to a disposable virtual
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

        # TODO:  Only allow pdf files
        for file_obj in files:

            # Do not attach context menu to a directory
            if file_obj.is_directory():
                return

            # Do not attach context menu  to anything other that a file
            # local files only; not remote
            if file_obj.get_uri_scheme() != 'file':
                return

            # Only attach context menu to pdf files
            filename, ext = os.path.splitext(file_obj.get_name())
            if ext and ext.lower() not in ['.pdf']:
                return

        menu_item = Nautilus.MenuItem(name='QubesMenuProvider::ConvertPdf',
                                      label='Convert To Trusted PDF',
                                      tip='',
                                      icon='')

        menu_item.connect('activate', self.on_menu_item_clicked, files)
        return menu_item,

    def on_menu_item_clicked(self, menu, files):
        '''Called when user chooses files though Nautilus context menu.
        '''
        for file_obj in files:

            # Check if file still exists
            if file_obj.is_gone():
                return

            gio_file = file_obj.get_location()
            cmd = (['/usr/lib/qubes/qvm-convert-pdf.gnome', gio_file.get_path()])
            pid = GLib.spawn_async(cmd)[0]
            GLib.spawn_close_pid(pid)
