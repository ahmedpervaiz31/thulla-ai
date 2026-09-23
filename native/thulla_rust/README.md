# Build (from repo root thulla-ai):
#   pip install maturin
#   cd native/thulla_rust
#   set PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1   # if Python > 3.13
#   python -m maturin develop --release
#
# Training auto-uses Rust via thulla_dmc.rust_env.make_env() when importable.
