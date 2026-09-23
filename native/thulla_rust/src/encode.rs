//! DMC observation encode matching thulla_dmc.encode.

use crate::card::{
    Card, ACTION_DIM, CARD_DIM, HISTORY_LEN, MAX_HAND, NUM_PLAYERS, TAKE_ASK_IDX, TAKE_PASS_IDX,
    X_NO_ACTION_DIM,
};
use crate::game::{Game, TrickState};
use crate::info::relative_seats;

pub fn cards_to_array(cards: &[Card]) -> [f32; CARD_DIM] {
    let mut arr = [0.0f32; CARD_DIM];
    for &c in cards {
        arr[c as usize] = 1.0;
    }
    arr
}

pub fn one_hot_size(n: usize) -> [f32; MAX_HAND] {
    let mut arr = [0.0f32; MAX_HAND];
    let n = n.min(MAX_HAND - 1);
    arr[n] = 1.0;
    arr
}

pub fn encode_action_card(card: Card) -> [f32; ACTION_DIM] {
    let mut arr = [0.0f32; ACTION_DIM];
    arr[card as usize] = 1.0;
    arr
}

pub fn encode_action_ask() -> [f32; ACTION_DIM] {
    let mut arr = [0.0f32; ACTION_DIM];
    arr[TAKE_ASK_IDX] = 1.0;
    arr
}

pub fn encode_action_pass() -> [f32; ACTION_DIM] {
    let mut arr = [0.0f32; ACTION_DIM];
    arr[TAKE_PASS_IDX] = 1.0;
    arr
}

pub fn encode_history(play_history: &[Card]) -> [[f32; CARD_DIM]; HISTORY_LEN] {
    let mut z = [[0.0f32; CARD_DIM]; HISTORY_LEN];
    let start = play_history.len().saturating_sub(HISTORY_LEN);
    let recent = &play_history[start..];
    let offset = HISTORY_LEN - recent.len();
    for (i, &card) in recent.iter().enumerate() {
        z[offset + i] = cards_to_array(&[card]);
    }
    z
}

pub fn encode_state(
    game: &Game,
    seat: usize,
    trick: Option<&TrickState>,
    play_history: &[Card],
    take_phase: bool,
    i_am_leader: bool,
) -> (Vec<f32>, Vec<f32>) {
    let my_cards = &game.hands[seat];
    // sync-like: hand sizes already on info; re-read from hands for encode
    let mut info = game.info.clone();
    info.sync_hands(&game.hands);

    let free = info.free_cards(seat, my_cards);
    let my_hand = cards_to_array(my_cards);
    let free_a = cards_to_array(&free);
    let trick_cards = cards_to_array(&info.trick_cards);

    let mut parts: Vec<f32> = Vec::with_capacity(X_NO_ACTION_DIM);
    parts.extend_from_slice(&my_hand);
    parts.extend_from_slice(&free_a);
    parts.extend_from_slice(&trick_cards);

    let mut size_parts: Vec<f32> = Vec::new();
    let mut void_parts: Vec<f32> = Vec::new();
    let mut known_parts: Vec<f32> = Vec::new();

    for rel in relative_seats(seat, NUM_PLAYERS) {
        size_parts.extend_from_slice(&one_hot_size(info.hand_sizes[rel]));
        if rel == seat {
            continue;
        }
        let vis: Vec<Card> = info.visible_cards(seat, rel, my_cards).into_iter().collect();
        known_parts.extend_from_slice(&cards_to_array(&vis));
        let mut v = [0.0f32; 4];
        for su in 0..4u8 {
            if info.voids[rel].contains(&su) {
                v[su as usize] = 1.0;
            }
        }
        void_parts.extend_from_slice(&v);
    }

    parts.extend_from_slice(&known_parts);

    let mut led = [0.0f32; 4];
    if let Some(t) = trick {
        if let Some(c) = t.colour {
            led[c as usize] = 1.0;
        }
    }
    parts.extend_from_slice(&led);

    let high = if let Some(t) = trick {
        if let Some(h) = t.highest_card {
            cards_to_array(&[h])
        } else {
            [0.0f32; CARD_DIM]
        }
    } else {
        [0.0f32; CARD_DIM]
    };
    parts.extend_from_slice(&high);

    let first = if trick.map(|t| t.first_trick).unwrap_or(false) {
        1.0
    } else {
        0.0
    };
    parts.push(first);
    parts.extend_from_slice(&size_parts);
    parts.extend_from_slice(&void_parts);
    parts.push(if take_phase { 1.0 } else { 0.0 });
    parts.push(if i_am_leader { 1.0 } else { 0.0 });

    assert_eq!(parts.len(), X_NO_ACTION_DIM, "x_no dim mismatch {}", parts.len());

    let z_mat = encode_history(play_history);
    let mut z_flat = Vec::with_capacity(HISTORY_LEN * CARD_DIM);
    for row in &z_mat {
        z_flat.extend_from_slice(row);
    }
    (parts, z_flat)
}

pub fn build_action_batch(
    x_no: &[f32],
    z_flat: &[f32],
    legal_actions: &[ActionEnc],
) -> (Vec<f32>, Vec<f32>) {
    let n = legal_actions.len();
    let mut x_batch = vec![0.0f32; n * crate::card::X_DIM];
    let mut z_batch = vec![0.0f32; n * HISTORY_LEN * CARD_DIM];
    for (i, act) in legal_actions.iter().enumerate() {
        let xo = i * crate::card::X_DIM;
        x_batch[xo..xo + X_NO_ACTION_DIM].copy_from_slice(x_no);
        let act_enc = match act {
            ActionEnc::Card(c) => encode_action_card(*c),
            ActionEnc::Ask => encode_action_ask(),
            ActionEnc::Pass => encode_action_pass(),
        };
        x_batch[xo + X_NO_ACTION_DIM..xo + crate::card::X_DIM].copy_from_slice(&act_enc);
        let zo = i * HISTORY_LEN * CARD_DIM;
        z_batch[zo..zo + HISTORY_LEN * CARD_DIM].copy_from_slice(z_flat);
    }
    (x_batch, z_batch)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ActionEnc {
    Card(Card),
    Ask,
    Pass,
}
