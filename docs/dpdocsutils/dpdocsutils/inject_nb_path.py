from nbformat import NotebookNode
from nbformat import v4 as nbf
import pathlib
import nbconvert
from functools import partial

def _on_notebook_start(notebook: NotebookNode, *, file_path: pathlib.Path):
    """Inject the path as a global variable `__dp_ipynb_file__"""
    cell = nbf.new_code_cell(source=f"__dp_ipynb_file__ = '{str(file_path)}'", metadata={"__dp_injected_remove__": True})
    cell["metadata"]["__dp_injected_remove__"] = True
    notebook["cells"].insert(0, cell)

def on_notebook_complete(notebook: NotebookNode):
    """Remove the injected path"""
    notebook["cells"] = [
            c for c in notebook["cells"]
            if not c.get("metadata", {}).get("__dp_injected_remove__", False)
        ]

def on_notebook_start_factory(fp):
    return partial(_on_notebook_start, file_path=fp)


class ExecutePreprocessor(nbconvert.preprocessors.ExecutePreprocessor):
    def __init__(self, *args, nb_file: pathlib.Path, **kwargs):
        self.__nb_file = nb_file
        super().__init__(*args, **kwargs)

    def preprocess(self, nb, resources):
        _on_notebook_start(nb, file_path=self.__nb_file)
        ret = super().preprocess(nb, resources)

        # this hook doesn't seem to fire, so execute it manually in our own postprocessor
        on_notebook_complete(nb)

        return ret
