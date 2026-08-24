from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class PortalStaticAssetTests(SimpleTestCase):
    def test_portal_runtime_assets_are_discoverable(self):
        required_assets = (
            'admin/assets/css/soft-ui-dashboard.css',
            'admin/assets/js/core/popper.min.js',
            'admin/assets/js/core/bootstrap.min.js',
            'admin/assets/js/plugins/perfect-scrollbar.min.js',
            'admin/assets/js/plugins/smooth-scrollbar.min.js',
            'admin/assets/js/soft-ui-dashboard.min.js',
            'admin/assets/img/apple-icon.png',
            'admin/assets/img/favicon.png',
        )

        missing_assets = [path for path in required_assets if finders.find(path) is None]

        self.assertEqual([], missing_assets, f'Missing portal static assets: {missing_assets}')
