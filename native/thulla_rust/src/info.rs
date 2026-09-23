//! PublicInfo subset needed for DMC encode (hard facts only).

use crate::card::{Card, CARD_DIM, NUM_PLAYERS};
use std::collections::BTreeSet;

#[derive(Clone, Debug)]
pub struct PublicInfo {
    pub player_cnt: usize,
    pub active_indices: Vec<usize>,
    pub discarded: BTreeSet<Card>,
    pub known_holdings: Vec<BTreeSet<Card>>,
    pub voids: Vec<BTreeSet<u8>>, // suit ids
    pub hand_sizes: Vec<usize>,
    pub led_suit: Option<u8>,
    pub current_highest: Option<Card>,
    pub current_highest_player: Option<usize>,
    pub trick_cards: Vec<Card>,
}

impl PublicInfo {
    pub fn new(player_cnt: usize) -> Self {
        let mut s = Self {
            player_cnt,
            active_indices: Vec::new(),
            discarded: BTreeSet::new(),
            known_holdings: vec![BTreeSet::new(); player_cnt],
            voids: vec![BTreeSet::new(); player_cnt],
            hand_sizes: vec![0; player_cnt],
            led_suit: None,
            current_highest: None,
            current_highest_player: None,
            trick_cards: Vec::new(),
        };
        s.reset((0..player_cnt).collect());
        s
    }

    pub fn reset(&mut self, active: Vec<usize>) {
        self.active_indices = active;
        self.discarded.clear();
        for k in &mut self.known_holdings {
            k.clear();
        }
        for v in &mut self.voids {
            v.clear();
        }
        self.hand_sizes = vec![0; self.player_cnt];
        self.clear_trick();
    }

    pub fn sync_hands(&mut self, hands: &[Vec<Card>]) {
        self.hand_sizes = hands.iter().map(|h| h.len()).collect();
    }

    fn clear_trick(&mut self) {
        self.led_suit = None;
        self.current_highest = None;
        self.current_highest_player = None;
        self.trick_cards.clear();
    }

    pub fn note_play(&mut self, player_idx: usize, card: Card, led_suit: Option<u8>) {
        self.known_holdings[player_idx].remove(&card);
        let su = crate::card::suit(card);
        self.voids[player_idx].remove(&su);
        if let Some(led) = led_suit {
            if su != led {
                self.voids[player_idx].insert(led);
            }
        }

        if led_suit.is_none() {
            self.led_suit = Some(su);
            self.current_highest = Some(card);
            self.current_highest_player = Some(player_idx);
        } else {
            let led = led_suit.unwrap();
            self.led_suit = Some(led);
            if su == led
                && (self.current_highest.is_none()
                    || crate::card::card_gt(card, self.current_highest.unwrap()))
            {
                self.current_highest = Some(card);
                self.current_highest_player = Some(player_idx);
            }
        }
        self.trick_cards.push(card);
        if self.hand_sizes[player_idx] > 0 {
            self.hand_sizes[player_idx] -= 1;
        }
    }

    pub fn finish_clean(&mut self, cards: &[Card]) {
        for c in cards {
            self.discarded.insert(*c);
        }
        self.clear_trick();
    }

    pub fn finish_thulla(&mut self, victim_idx: usize, cards: &[Card]) {
        for card in cards {
            self.known_holdings[victim_idx].insert(*card);
            self.voids[victim_idx].remove(&crate::card::suit(*card));
        }
        self.hand_sizes[victim_idx] += cards.len();
        self.clear_trick();
    }

    pub fn note_take(&mut self, taker_idx: usize, target_idx: usize, cards: &[Card]) {
        let known: Vec<Card> = self.known_holdings[target_idx].iter().copied().collect();
        for card in &known {
            self.known_holdings[taker_idx].insert(*card);
            self.voids[taker_idx].remove(&crate::card::suit(*card));
        }
        self.known_holdings[target_idx].clear();
        self.voids[target_idx].clear();
        let n = cards.len();
        self.hand_sizes[taker_idx] += n;
        self.hand_sizes[target_idx] = 0;
    }

    pub fn note_got_away(&mut self, idx: usize) {
        if let Some(pos) = self.active_indices.iter().position(|&x| x == idx) {
            self.active_indices.remove(pos);
        }
    }

    pub fn unassigned_cards(&self, my_hand: &[Card]) -> Vec<Card> {
        let mut seen = self.discarded.clone();
        for c in my_hand {
            seen.insert(*c);
        }
        for set in &self.known_holdings {
            for c in set {
                seen.insert(*c);
            }
        }
        for c in &self.trick_cards {
            seen.insert(*c);
        }
        (0..CARD_DIM as u8).filter(|c| !seen.contains(c)).collect()
    }

    pub fn heads_up_opponent(&self, me: usize) -> Option<usize> {
        if self.active_indices.len() != 2 || !self.active_indices.contains(&me) {
            return None;
        }
        self.active_indices.iter().copied().find(|&p| p != me)
    }

    pub fn cannot_hold(&self, player_idx: usize, card: Card) -> bool {
        self.voids[player_idx].contains(&crate::card::suit(card))
    }

    pub fn deduced_hand(&self, me: usize, player_idx: usize, my_hand: &[Card]) -> Option<BTreeSet<Card>> {
        if player_idx == me {
            return Some(my_hand.iter().copied().collect());
        }
        let opp = self.heads_up_opponent(me)?;
        if player_idx != opp {
            return None;
        }
        let known = &self.known_holdings[player_idx];
        let free = self.unassigned_cards(my_hand);
        for card in &free {
            if self.cannot_hold(player_idx, *card) {
                return None;
            }
        }
        let mut full = known.clone();
        for c in free {
            full.insert(c);
        }
        if full.len() != self.hand_sizes[player_idx] {
            return None;
        }
        Some(full)
    }

    pub fn visible_cards(&self, me: usize, player_idx: usize, my_hand: &[Card]) -> BTreeSet<Card> {
        if let Some(d) = self.deduced_hand(me, player_idx, my_hand) {
            d
        } else {
            self.known_holdings[player_idx].clone()
        }
    }

    pub fn free_cards(&self, me: usize, my_hand: &[Card]) -> Vec<Card> {
        if let Some(opp) = self.heads_up_opponent(me) {
            if self.deduced_hand(me, opp, my_hand).is_some() {
                return Vec::new();
            }
        }
        self.unassigned_cards(my_hand)
    }
}

pub fn relative_seats(me: usize, n: usize) -> Vec<usize> {
    (0..n).map(|i| (me + i) % n).collect()
}

#[allow(dead_code)]
pub fn assert_dims() {
    assert_eq!(NUM_PLAYERS, 4);
}
