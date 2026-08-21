import os

from django.contrib.staticfiles.finders import FileSystemFinder


class PortablePrefixedFileSystemFinder(FileSystemFinder):
    """Resolve URL-style paths in prefixed STATICFILES_DIRS on every OS."""

    def find_location(self, root, path, prefix=None):
        normalized_path = str(path).replace('/', os.sep).replace('\\', os.sep)
        return super().find_location(root, normalized_path, prefix)
