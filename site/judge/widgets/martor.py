from martor.widgets import AdminMartorWidget as OldAdminMartorWidget, MartorWidget as OldMartorWidget

__all__ = ['MartorWidget', 'AdminMartorWidget']


class MartorWidget(OldMartorWidget):
    class Media:
        css = {
            'all': ['martor-description.css'],
        }
        js = ['martor-mathjax.js']


class AdminMartorWidget(OldAdminMartorWidget):
    UPLOADS_ENABLED = False

    class Media:
        css = {
            'all': MartorWidget.Media.css['all'] + ['guide-image-library.css'],
        }
        js = ['admin/js/jquery.init.js', 'martor-mathjax.js', 'guide-image-library.js']
