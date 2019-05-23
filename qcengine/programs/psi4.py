"""
Calls the Psi4 executable.
"""
import json
from typing import Dict

from qcelemental.models import Result
from qcelemental.util import parse_version, safe_version, which

from .executor import ProgramExecutor
from ..exceptions import InputError, RandomError, ResourceError, UnknownError
from ..util import execute, popen


class Psi4Executor(ProgramExecutor):

    _defaults = {
        "name": "Psi4",
        "scratch": True,
        "thread_safe": False,
        "thread_parallel": True,
        "node_parallel": False,
        "managed_memory": True,
    }
    version_cache: Dict[str, str] = {}

    class Config(ProgramExecutor.Config):
        pass

    def __init__(self, **kwargs):
        super().__init__(**{**self._defaults, **kwargs})

    @staticmethod
    def found(raise_error: bool=False) -> bool:
        return which('psi4', return_bool=True, raise_error=raise_error, raise_msg='Please install via `conda install psi4 -c psi4`.')

    def get_version(self) -> str:
        self.found(raise_error=True)

        which_prog = which('psi4')
        if which_prog not in self.version_cache:
            with popen([which_prog, '--version']) as exc:
                exc["proc"].wait(timeout=15)
            self.version_cache[which_prog] = safe_version(exc["stdout"])

        candidate_version = self.version_cache[which_prog]

        if "undef" in candidate_version:
            raise TypeError(
                "Using custom build without tags. Please pull git tags with `git pull origin master --tags`.")

        return candidate_version

    def compute(self, input_model: 'ResultInput', config: 'JobConfig') -> 'Result':
        """
        Runs Psi4 in API mode
        """
        self.found(raise_error=True)

        # Setup the job
        input_data = input_model.json_dict()
        input_data["nthreads"] = config.ncores
        input_data["memory"] = int(config.memory * 1024 * 1024 * 1024 * 0.95)  # Memory in bytes
        input_data["success"] = False
        input_data["return_output"] = True

        if input_data["schema_name"] == "qcschema_input":
            input_data["schema_name"] = "qc_schema_input"

        if config.scratch_directory:
            input_data["scratch_location"] = config.scratch_directory

        if parse_version(self.get_version()) > parse_version("1.2"):

            caseless_keywords = {k.lower(): v for k, v in input_model.keywords.items()}
            if (input_model.molecule.molecular_multiplicity != 1) and ("reference" not in caseless_keywords):
                input_data["keywords"]["reference"] = "uhf"

            # Execute the program
            success, output = execute([which("psi4"), "--json", "data.json"], {"data.json": json.dumps(input_data)},
                                      ["data.json"])

            if success:
                output_data = json.loads(output["outfiles"]["data.json"])
                if "extras" not in output_data:
                    output_data["extras"] = {}

                output_data["extras"]["local_qcvars"] = output_data.pop("psi4:qcvars", None)
                if output_data["success"] is False:
                    if "error_message" not in output_data["error"]:
                        # older c. 1.3 message-only run_json
                        output_data["error"] = {"error_type": "internal_error", "error_message": output_data["error"]}
            else:
                output_data = input_data
                output_data["error"] = {"error_type": "execution_error", "error_message": output["stderr"]}

        else:
            raise ResourceError("Psi4 version '{}' not understood.".format(self.get_version()))

        # Reset the schema if required
        output_data["schema_name"] = "qcschema_output"

        # Dispatch errors, PSIO Errors are not recoverable for future runs
        if output_data["success"] is False:
            error_message = output_data["error"]["error_message"]

            if "PSIO Error" in error_message:
                if "scratch directory" in error_message:
                    # Psi4 cannot access the folder or file
                    raise ResourceError(error_message)
                else:
                    # Likely a random error, worth retrying
                    raise RandomError(error_message)
            elif "SIGSEV" in error_message:
                raise RandomError(error_message)
            elif "TypeError: set_global_option" in error_message:
                raise InputError(error_message)
            elif "RHF reference is only for singlets" in error_message:
                raise InputError(error_message)
            else:
                raise UnknownError(error_message)

        # Move several pieces up a level
        output_data["provenance"]["memory"] = round(output_data.pop("memory") / (1024**3), 3)  # Move back to GB
        output_data["provenance"]["nthreads"] = output_data.pop("nthreads")
        output_data["stdout"] = output_data.pop("raw_output", None)

        # Delete keys
        output_data.pop("return_output", None)
        output_data.pop("scratch_location", None)

        return Result(**output_data)
