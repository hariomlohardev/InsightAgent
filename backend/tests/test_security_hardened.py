import pytest
from app.core.security import validate_code, SecurityError

def test_block_time_import():
    with pytest.raises(SecurityError):
        validate_code("import time\ntime.sleep(1)")

def test_block_from_os_import():
    with pytest.raises(SecurityError):
        validate_code("from os import path")

def test_block_os_path():
    with pytest.raises(SecurityError):
        validate_code("import os.path\nos.path.join('a','b')")

def test_block_importlib():
    with pytest.raises(SecurityError):
        validate_code("import importlib\nimportlib.import_module('os')")

def test_block_ctypes():
    with pytest.raises(SecurityError):
        validate_code("import ctypes")

def test_block_dunder_import():
    with pytest.raises(SecurityError):
        validate_code("__import__('os').system('ls')")

def test_block_threading():
    with pytest.raises(SecurityError):
        validate_code("import threading\nthreading.Thread(target=lambda: None)")

def test_allow_safe_still():
    validate_code("result = df.groupby('A')['B'].sum()\nfig = px.bar(result, x='A', y='B')")
    validate_code("result = duckdb.query('SELECT * FROM df').to_df()")
    validate_code("import pandas as pd\nresult = df.head()")  # pandas is allowed? Check - our blocked list doesn't include pandas, so allowed

def test_block_open_via_call():
    with pytest.raises(SecurityError):
        validate_code("open('file.txt')")

def test_block_eval_via_call():
    with pytest.raises(SecurityError):
        validate_code("eval('1+1')")
