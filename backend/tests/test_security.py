import pytest
from app.core.security import validate_code, SecurityError


def test_block_os_import():
    with pytest.raises(SecurityError):
        validate_code("import os\nos.system('ls')")


def test_block_subprocess():
    with pytest.raises(SecurityError):
        validate_code("import subprocess\nsubprocess.call(['ls'])")


def test_block_eval():
    with pytest.raises(SecurityError):
        validate_code("eval('1+1')")


def test_block_dunder():
    with pytest.raises(SecurityError):
        validate_code("x = df.__class__")


def test_allow_safe():
    # Should not raise
    validate_code(
        "result = df.groupby('A')['B'].sum().reset_index()\nfig = px.bar(result, x='A', y='B')"
    )
    validate_code("import pandas as pd\nresult = df.head()")
    validate_code("result = df.describe()")
