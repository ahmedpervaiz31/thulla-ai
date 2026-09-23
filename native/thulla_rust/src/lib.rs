mod card;
mod encode;
mod env;
mod game;
mod info;

use card::{card_code, parse_card_code, CARD_DIM, HISTORY_LEN, X_DIM, X_NO_ACTION_DIM};
use encode::ActionEnc;
use env::{Env, Phase};
use numpy::{PyArray1, PyArray2, PyArrayMethods};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

fn action_to_code(a: &ActionEnc) -> usize {
    match a {
        ActionEnc::Card(c) => *c as usize,
        ActionEnc::Ask => 52,
        ActionEnc::Pass => 53,
    }
}

fn action_to_py(py: Python<'_>, a: &ActionEnc) -> PyObject {
    match a {
        ActionEnc::Card(c) => card_code(*c).into_py(py),
        ActionEnc::Ask => "ASK".into_py(py),
        ActionEnc::Pass => "PASS".into_py(py),
    }
}

fn obs_to_dict(py: Python<'_>, obs: &env::Obs) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("position", obs.position)?;
    d.set_item(
        "phase",
        match obs.phase {
            Phase::Play => "play",
            Phase::Take => "take",
        },
    )?;
    let legal = PyList::empty_bound(py);
    for a in &obs.legal {
        legal.append(action_to_py(py, a))?;
    }
    d.set_item("legal_actions", legal)?;

    let x_no = PyArray1::from_slice_bound(py, &obs.x_no);
    d.set_item("x_no_action", x_no)?;

    let z = PyArray2::from_vec2_bound(
        py,
        &(0..HISTORY_LEN)
            .map(|r| obs.z_flat[r * CARD_DIM..(r + 1) * CARD_DIM].to_vec())
            .collect::<Vec<_>>(),
    )?;
    d.set_item("z", z)?;

    let n = obs.legal.len();
    let x_batch = PyArray2::from_vec2_bound(
        py,
        &(0..n)
            .map(|i| {
                obs.x_batch[i * X_DIM..(i + 1) * X_DIM].to_vec()
            })
            .collect::<Vec<_>>(),
    )?;
    let z_batch = PyArray2::from_vec2_bound(
        py,
        // Actually z_batch is (n, HISTORY_LEN, CARD_DIM) — expose as (n, HISTORY_LEN*CARD_DIM) flat rows? 
        // Python expects (n, 20, 52). Build 3D via list of 2D or reshape in Python.
        // Use (n, HISTORY_LEN * CARD_DIM) and document reshape; better build properly.
        &(0..n)
            .map(|i| {
                obs.z_batch[i * HISTORY_LEN * CARD_DIM..(i + 1) * HISTORY_LEN * CARD_DIM].to_vec()
            })
            .collect::<Vec<_>>(),
    )?;
    d.set_item("x_batch", x_batch)?;
    d.set_item("z_batch_flat", z_batch)?;
    d.set_item("x_no_action_dim", X_NO_ACTION_DIM)?;
    Ok(d.into())
}

#[pyclass(name = "RustEnv")]
struct PyRustEnv {
    inner: Env,
}

#[pymethods]
impl PyRustEnv {
    #[new]
    fn new() -> Self {
        Self { inner: Env::new() }
    }

    fn reset(&mut self, py: Python<'_>, seed: u64) -> PyResult<PyObject> {
        let obs = self.inner.reset_with_seed(seed);
        obs_to_dict(py, &obs)
    }

    /// hands: list[list[str card codes]], ace_holder seat index
    fn reset_hands(
        &mut self,
        py: Python<'_>,
        hands: Vec<Vec<String>>,
        ace_holder: usize,
    ) -> PyResult<PyObject> {
        let mut parsed = Vec::with_capacity(hands.len());
        for h in hands {
            let mut ph = Vec::new();
            for c in h {
                let card = parse_card_code(&c)
                    .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("bad card {c}")))?;
                ph.push(card);
            }
            parsed.push(ph);
        }
        let obs = self.inner.reset_with_hands(parsed, ace_holder);
        obs_to_dict(py, &obs)
    }

    fn legal_codes(&self) -> Vec<usize> {
        self.inner
            .legal_actions()
            .iter()
            .map(action_to_code)
            .collect()
    }

    fn step(&mut self, py: Python<'_>, action_code: usize) -> PyResult<PyObject> {
        let (obs, rewards, done) = self.inner.step(action_code);
        let d = PyDict::new_bound(py);
        if let Some(o) = obs {
            d.set_item("obs", obs_to_dict(py, &o)?)?;
        } else {
            d.set_item("obs", py.None())?;
        }
        d.set_item("rewards", rewards.to_vec())?;
        d.set_item("done", done)?;
        Ok(d.into())
    }

    fn current_seat(&self) -> usize {
        self.inner.current_seat()
    }

    fn hands_codes(&self) -> Vec<Vec<String>> {
        self.inner
            .game
            .hands
            .iter()
            .map(|h| h.iter().copied().map(card_code).collect())
            .collect()
    }
}

#[pymodule]
fn thulla_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyRustEnv>()?;
    m.add("X_NO_ACTION_DIM", X_NO_ACTION_DIM)?;
    m.add("X_DIM", X_DIM)?;
    m.add("Z_ROWS", HISTORY_LEN)?;
    m.add("Z_DIM", CARD_DIM)?;
    Ok(())
}
