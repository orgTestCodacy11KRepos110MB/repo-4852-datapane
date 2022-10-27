#!/usr/bin/env python

import datapane
dp_version = datapane.__version__
import os
os.environ["DATAPANE_CDN_BASE"] = f"https://staging.datapane-cdn.com/v{dp_version}"


# clear up ignored stale files
import glob
stale_files = glob.glob("docs/**.html", recursive=True) + glob.glob("docs/**-preview.png", recursive=True)
for f in stale_files:
    os.remove(f)

import pathlib
import nbformat
import nbconvert
import dpdocsutils.inject_nb_path
# execute the notebooks
cwd = pathlib.Path.cwd()
for f in glob.glob("docs/**/*.ipynb", recursive=True):
    # we need to be in their directory
    path = pathlib.Path(f).absolute()

    try:
        os.chdir(path.parent)
        # execute the notebooks using nbconvert
        nb = nbformat.read(path, as_version=4)
        ep = dpdocsutils.inject_nb_path.ExecutePreprocessor(
            timeout=-1,
            nb_file=path,
        )

        cm = nbconvert.preprocessors.ClearMetadataPreprocessor(
            preserve_cell_metadata_mask=["tags", "__dp_injected_remove__"],
        )
        ep.preprocess(nb, {"metadata": {"path": path.parent}})
        cm.preprocess(nb, {"metadata": {"path": path.parent}})
        nbformat.write(nb, path)
    finally:
        os.chdir(cwd)
