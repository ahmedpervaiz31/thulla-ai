//! Card as dense index 0..51 matching Python encode.card_index:
//! colour order Diamond, Heart, Spade, Club; ranks 2..A.

pub const NUM_PLAYERS: usize = 4;
pub const CARD_DIM: usize = 52;
pub const HISTORY_LEN: usize = 20;
pub const MAX_HAND: usize = 14;
pub const ACTION_DIM: usize = 54;
pub const TAKE_ASK_IDX: usize = 52;
pub const TAKE_PASS_IDX: usize = 53;
pub const X_NO_ACTION_DIM: usize = 439;
pub const X_DIM: usize = X_NO_ACTION_DIM + ACTION_DIM;

pub type Card = u8; // 0..51

#[inline]
pub fn suit(c: Card) -> u8 {
    c / 13
}

#[inline]
pub fn rank(c: Card) -> u8 {
    c % 13
}

#[inline]
pub fn make_card(suit: u8, rank: u8) -> Card {
    suit * 13 + rank
}

pub const ACE_SPADES: Card = 2 * 13 + 12; // Spade=2, A=12

pub fn full_deck() -> [Card; 52] {
    let mut d = [0u8; 52];
    for i in 0..52 {
        d[i] = i as u8;
    }
    d
}

/// Compact code like Python Card.code(): "AS", "10H", "2D"
pub fn card_code(c: Card) -> String {
    let ranks = [
        "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A",
    ];
    let suits = ["D", "H", "S", "C"];
    format!("{}{}", ranks[rank(c) as usize], suits[suit(c) as usize])
}

pub fn parse_card_code(s: &str) -> Option<Card> {
    let t = s.trim().to_uppercase().replace([' ', '-'], "");
    let ranks = [
        "10", "2", "3", "4", "5", "6", "7", "8", "9", "J", "Q", "K", "A",
    ];
    // try longest rank first
    let mut rank_names = ranks.to_vec();
    rank_names.sort_by_key(|r| std::cmp::Reverse(r.len()));
    for rname in rank_names {
        if t.starts_with(rname) {
            let rest = &t[rname.len()..];
            let su = match rest {
                "D" | "DIAMOND" | "DIAMONDS" => 0u8,
                "H" | "HEART" | "HEARTS" => 1,
                "S" | "SPADE" | "SPADES" => 2,
                "C" | "CLUB" | "CLUBS" => 3,
                _ => return None,
            };
            let ri = match rname {
                "2" => 0,
                "3" => 1,
                "4" => 2,
                "5" => 3,
                "6" => 4,
                "7" => 5,
                "8" => 6,
                "9" => 7,
                "10" => 8,
                "J" => 9,
                "Q" => 10,
                "K" => 11,
                "A" => 12,
                _ => return None,
            };
            return Some(make_card(su, ri));
        }
    }
    None
}

pub fn cards_of_suit(su: u8) -> [Card; 13] {
    let mut out = [0u8; 13];
    for r in 0..13u8 {
        out[r as usize] = make_card(su, r);
    }
    out
}

pub fn valid_moves(hand: &[Card], expected: Option<&[Card]>) -> Vec<Card> {
    match expected {
        None => hand.to_vec(),
        Some(exp) => {
            let common: Vec<Card> = hand.iter().copied().filter(|c| exp.contains(c)).collect();
            if common.is_empty() {
                hand.to_vec()
            } else {
                common
            }
        }
    }
}

#[inline]
pub fn card_gt(a: Card, b: Card) -> bool {
    // Same-suit compare by rank (Python only compares rank via __lt__)
    rank(a) > rank(b)
}
