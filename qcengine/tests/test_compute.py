"""
Tests the DQM compute dispatch module
"""

import copy

import pytest
from qcelemental.models import Molecule, ResultInput

import qcengine as qcng
from qcengine import testing

_base_json = {"schema_name": "qcschema_input", "schema_version": 1}


def test_missing_key():
    ret = qcng.compute({"hello": "hi"}, "bleh")
    assert ret["success"] is False
    assert "hello" in ret or ("input_data" in ret and "hello" in ret["input_data"])


@testing.using_psi4
def test_psi4_task():
    json_data = copy.deepcopy(_base_json)
    json_data["molecule"] = qcng.get_molecule("water")
    json_data["driver"] = "energy"
    json_data["model"] = {"method": "SCF", "basis": "sto-3g"}
    json_data["keywords"] = {"scf_type": "df"}

    ret = qcng.compute(json_data, "psi4", raise_error=True, capture_output=False)

    assert ret["driver"] == "energy"
    assert "provenance" in ret
    assert "Final Energy" in ret["stdout"]

    for key in ["cpu", "hostname", "username", "wall_time"]:
        assert key in ret["provenance"]

    assert ret["success"] is True


@testing.using_psi4
def test_psi4_ref_switch():
    inp = ResultInput(**{
        "molecule": {
            "symbols": ["Li"],
            "geometry": [0, 0, 0],
            "molecular_multiplicity": 2
        },
        "driver": "energy",
        "model": {
            "method": "SCF",
            "basis": "sto-3g"
        },
        "keywords": {
            "scf_type": "df"
        }
    })

    ret = qcng.compute(inp, "psi4", raise_error=True, return_dict=False)

    assert ret.success is True
    assert ret.properties.calcinfo_nalpha == 2
    assert ret.properties.calcinfo_nbeta == 1


@testing.using_rdkit
def test_rdkit_task():
    json_data = copy.deepcopy(_base_json)
    json_data["molecule"] = qcng.get_molecule("water")
    json_data["driver"] = "gradient"
    json_data["model"] = {"method": "UFF", "basis": ""}
    json_data["keywords"] = {}
    json_data["return_output"] = False

    ret = qcng.compute(json_data, "rdkit", raise_error=True)

    assert ret["success"] is True


@testing.using_rdkit
def test_rdkit_connectivity_error():
    json_data = copy.deepcopy(_base_json)
    json_data["molecule"] = qcng.get_molecule("water").dict()
    json_data["driver"] = "gradient"
    json_data["model"] = {"method": "UFF", "basis": ""}
    json_data["keywords"] = {}
    json_data["return_output"] = False
    del json_data["molecule"]["connectivity"]

    ret = qcng.compute(json_data, "rdkit")
    assert ret["success"] is False
    assert "error" in ret
    assert "connectivity" in ret["error"]["error_message"]

    with pytest.raises(ValueError):
        qcng.compute(json_data, "rdkit", raise_error=True)


@testing.using_torchani
def test_torchani_task():
    json_data = copy.deepcopy(_base_json)
    json_data["molecule"] = qcng.get_molecule("water")
    json_data["driver"] = "gradient"
    json_data["model"] = {"method": "ANI1", "basis": None}
    json_data["keywords"] = {}
    json_data["return_output"] = False

    ret = qcng.compute(json_data, "torchani", raise_error=True)

    assert ret["success"] is True
    assert ret["driver"] == "gradient"
    assert "provenance" in ret
