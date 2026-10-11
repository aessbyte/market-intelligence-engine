import json
import unittest
from importlib.resources import files

import jsonschema

from market_intelligence.engine import analyze

from tests.fixtures import snapshot


class SchemaTests(unittest.TestCase):
    def test_ok_and_degraded_match_schema(self) -> None:
        schema = json.loads(files("market_intelligence").joinpath("result.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        data = snapshot()
        for degraded in (False, True):
            if degraded:
                del data["klines"]["H1"]
            # Validate actual JSON types, not Python tuples from frozen dataclasses.
            result = json.loads(json.dumps(analyze(data), allow_nan=False))
            jsonschema.validate(result, schema)
            result["scenarios"][0]["probability"] = 0.9
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(result, schema)
