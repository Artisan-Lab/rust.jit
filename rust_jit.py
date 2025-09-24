# rust_jit.py
import os
import sys
import tempfile
import subprocess
import shutil
import ctypes
import hashlib
from types import SimpleNamespace
from pathlib import Path

def _platform_libname(basename: str) -> str:
    if sys.platform.startswith("linux"):
        return f"lib{basename}.so"
    if sys.platform == "darwin":
        return f"lib{basename}.dylib"
    if sys.platform == "win32":
        return f"{basename}.dll"
    return f"lib{basename}.so"

def _ensure_cargo_exists():
    if shutil.which("cargo") is None:
        raise RuntimeError("cargo (Rust toolchain) not found in PATH. Please install Rust and cargo.")

def _hash_src(src: str) -> str:
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]

def rust_jit(rust_src: str, fn_name: str, argtypes=(), restype=ctypes.c_int, crate_name: str = None, cargo_extra_args=None):
    """
    Decorator factory:
      - rust_src: complete Rust source code (must include the exported #[no_mangle] pub extern "C" fn ...)
      - fn_name: the name of the exported function to load (string)
      - argtypes/restype: ctypes argument and return types
      - crate_name: optional crate name; defaults to a hash of the source code to avoid conflicts
    Returns a decorator that replaces the placeholder Python function with a callable ctypes wrapper.
    """
    cargo_extra_args = cargo_extra_args or []
    _ensure_cargo_exists()
    src_hash = _hash_src(rust_src)
    crate_name = crate_name or f"rustjit_{src_hash}"

    def decorator(pyfunc):
        tempdir = Path(tempfile.gettempdir()) / f"rustjit_{crate_name}"
        rebuild = True
        lib_path = None

        if not tempdir.exists():
            tempdir.mkdir(parents=True, exist_ok=True)

        src_file = tempdir / "src" / "lib.rs"
        cargo_toml = tempdir / "Cargo.toml"

        if src_file.exists():
            existing = src_file.read_text(encoding='utf-8')
            if existing == rust_src:
                # check target dir
                target_dir = tempdir / "target" / "release"
                libname = _platform_libname(crate_name)
                candidate = target_dir / libname
                if candidate.exists():
                    lib_path = str(candidate.resolve())
                    rebuild = False

        if rebuild:
            # write to Cargo.toml
            (tempdir / "src").mkdir(exist_ok=True)
            cargo_toml.write_text(f"""[package]
name = "{crate_name}"
version = "0.1.0"
edition = "2021"

[lib]
name = "{crate_name}"
crate-type = ["cdylib"]
""", encoding='utf-8')
            # write to src/lib.rs
            src_file.write_text(rust_src, encoding='utf-8')

            build_cmd = ["cargo", "build", "--release"]
            try:
                subprocess.run(build_cmd, cwd=str(tempdir), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                out = e.stdout.decode(errors='ignore') if e.stdout else ""
                err = e.stderr.decode(errors='ignore') if e.stderr else ""
                raise RuntimeError(f"Rust compilation failed.\nSTDOUT:\n{out}\nSTDERR:\n{err}")

            target_dir = tempdir / "target" / "release"
            libname = _platform_libname(crate_name)
            candidate = target_dir / libname
            if not candidate.exists():
                found = list(target_dir.rglob(libname))
                if found:
                    candidate = found[0]
                else:
                    raise RuntimeError(f"Cannot find the library: {libname} (searched under {target_dir})")
            lib_path = str(candidate.resolve())

        # Load the dynamic lib via ctypes
        cdll = ctypes.CDLL(lib_path)

        try:
            cfn = getattr(cdll, fn_name)
        except AttributeError:
            raise RuntimeError(f"Cannot find the function: '{fn_name}'. Ensure using #[no_mangle] when define the function pub extern \"C\" fn {fn_name}(...).")

        cfn.argtypes = argtypes
        cfn.restype = restype

        def wrapper(*args, **kwargs):
            if kwargs:
                raise TypeError("Unsupported")
            return cfn(*args)

        wrapper.__name__ = pyfunc.__name__
        wrapper.__doc__ = pyfunc.__doc__
        wrapper.__source_lib__ = lib_path
        wrapper.__rust_fn__ = fn_name
        return wrapper
 
    return decorator

# To use the decorator as rust.jit
rust = SimpleNamespace(jit=rust_jit)
