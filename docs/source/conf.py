# Sphinx configuration for the scene-streamer documentation.
import os
import sys

if os.environ.get("READTHEDOCS") != "True":
    # use the checkout when building locally; on Read the Docs the installed package is used
    sys.path.insert(0, os.path.abspath("../../"))

import scene_streamer

project = "scene-streamer"
author = "The Menpo Team"
release = version = scene_streamer.__version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

master_doc = "index"
autodoc_member_order = "bysource"
html_theme = "sphinx_rtd_theme"
