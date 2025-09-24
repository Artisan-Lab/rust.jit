from rust_jit import rust
import ctypes

# case 1
@rust.jit(
    rust_src = r'''
        #[no_mangle]
        pub extern "C" fn add_i32(a: i32, b: i32) -> i32 {
            a + b
        }
    ''',
    fn_name='add_i32',
    argtypes=(ctypes.c_int, ctypes.c_int),
    restype=ctypes.c_int,
)
def add_i32(a, b):
    pass

print(add_i32(10, 23))  # => 33

# case 2 
RUST_SRC = r'''
use std::ffi::CString;
use std::os::raw::c_char;

#[no_mangle]
pub extern "C" fn greet(name: *const c_char) -> *mut c_char {
    unsafe {
        if name.is_null() {
            let s = CString::new("Hello, stranger!").unwrap();
            return s.into_raw();
        } else {
            let cstr = std::ffi::CStr::from_ptr(name);
            let rust_str = cstr.to_string_lossy();
            let s = CString::new(format!("Hello, {}!", rust_str)).unwrap();
            return s.into_raw();
        }
    }
}
'''

@rust.jit(
    rust_src=RUST_SRC,
    fn_name="greet",
    argtypes=(ctypes.c_char_p,),
    restype=ctypes.c_char_p,
)
def greet(name):
    pass

print(greet(b"Alice").decode())   # Hello, Alice!
