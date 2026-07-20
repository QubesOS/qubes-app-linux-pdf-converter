import os
import subprocess
import sys

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath("../"))
sys.path.insert(1, os.path.abspath("../test-packages"))

# -- Project information -----------------------------------------------------

project = "app-linux-pdf-converter"
author = "Qubes OS Project"
copyright = "2010-%Y, Invisible Things Lab"

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
version = open("../version").read().strip()
# The full version, including alpha/beta/rc tags.
try:
    release = (
        subprocess.check_output(["git", "describe", "--long", "--dirty"])
        .strip()
        .decode()
    )
except:
    release = "1"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.intersphinx",  # Reference other doc projects
]

# -- Extensions configuration ------------------------------------------------
# Allows references to the docs in dev.qubes-os.org
# i.e.: :doc:`core-admin:libvirt`
intersphinx_mapping = {
    "qubes-doc": ("https://doc.qubes-os.org/en/latest/", None),
    "core-admin": ("https://dev.qubes-os.org/projects/core-admin/en/latest/", None),
    "core-admin-client": (
        "https://dev.qubes-os.org/projects/core-admin-client/en/latest/",
        None,
    ),
    "core-qrexec": (
        "https://dev.qubes-os.org/projects/qubes-core-qrexec/en/stable/",
        None,
    ),
}

intersphinx_disabled_reftypes = []

# -- Options for markup --------------------------------------------------------

option_emphasise_placeholders = True

# -- -- Options for the nitpicky mode ------------------------------------------

nitpicky = True
