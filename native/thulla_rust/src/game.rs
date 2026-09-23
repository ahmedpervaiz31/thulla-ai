//! 4-player ThullaGame core used by the DMC env.

use crate::card::{
    card_gt, cards_of_suit, valid_moves, Card, ACE_SPADES, NUM_PLAYERS,
};
use crate::info::PublicInfo;

#[derive(Clone, Debug)]
pub struct TrickState {
    pub leader_idx: usize,
    pub first_trick: bool,
    pub order: Vec<usize>,
    pub colour: Option<u8>,
    pub stack: Vec<Card>,
    pub highest_card: Option<Card>,
    pub highest_idx: Option<usize>,
    pub seat_pos: usize,
    pub done: bool,
    pub result: Option<&'static str>,
    pub next_leader: Option<usize>,
    pub thulla_by: Option<usize>,
}

#[derive(Clone, Debug)]
pub struct Game {
    pub hands: Vec<Vec<Card>>,
    pub player_cnt: usize,
    pub ace_spades_holder_idx: usize,
    pub winners: Vec<usize>,
    pub active_player_indices: Vec<usize>,
    pub trick_number: usize,
    pub info: PublicInfo,
}

impl Game {
    pub fn new(player_cnt: usize) -> Self {
        assert_eq!(player_cnt, NUM_PLAYERS);
        Self {
            hands: vec![Vec::new(); player_cnt],
            player_cnt,
            ace_spades_holder_idx: 0,
            winners: Vec::new(),
            active_player_indices: (0..player_cnt).collect(),
            trick_number: 0,
            info: PublicInfo::new(player_cnt),
        }
    }

    pub fn set_hands(&mut self, hands: Vec<Vec<Card>>, ace_holder: Option<usize>) {
        assert_eq!(hands.len(), self.player_cnt);
        self.hands = hands;
        for h in &mut self.hands {
            h.sort_by_key(|c| (crate::card::suit(*c), crate::card::rank(*c)));
        }
        self.active_player_indices = (0..self.player_cnt)
            .filter(|&i| !self.hands[i].is_empty())
            .collect();
        self.winners.clear();
        if let Some(a) = ace_holder {
            self.ace_spades_holder_idx = a;
        } else {
            self.ace_spades_holder_idx = self
                .hands
                .iter()
                .position(|h| h.contains(&ACE_SPADES))
                .unwrap_or(0);
        }
        self.info.reset(self.active_player_indices.clone());
        self.info.sync_hands(&self.hands);
    }

    pub fn deal_from_deck(&mut self, deck: &[Card]) {
        assert_eq!(deck.len(), 52);
        for h in &mut self.hands {
            h.clear();
        }
        for (i, &card) in deck.iter().enumerate() {
            let turn = i % self.player_cnt;
            if card == ACE_SPADES {
                self.ace_spades_holder_idx = turn;
            }
            self.hands[turn].push(card);
        }
        for h in &mut self.hands {
            h.sort_by_key(|c| (crate::card::suit(*c), crate::card::rank(*c)));
        }
        self.active_player_indices = (0..self.player_cnt).collect();
        self.winners.clear();
        self.info.reset(self.active_player_indices.clone());
        self.info.sync_hands(&self.hands);
    }

    pub fn next_active(&self, from_idx: usize) -> Option<usize> {
        for i in 1..=self.player_cnt {
            let idx = (from_idx + i) % self.player_cnt;
            if self.active_player_indices.contains(&idx) {
                return Some(idx);
            }
        }
        None
    }

    pub fn ensure_leader_active(&self, leader_idx: Option<usize>) -> Option<usize> {
        let Some(l) = leader_idx else {
            return None;
        };
        if self.active_player_indices.contains(&l) {
            Some(l)
        } else {
            self.next_active(l)
        }
    }

    pub fn active_in_order(&self, start_idx: usize) -> Vec<usize> {
        let start = if self.active_player_indices.contains(&start_idx) {
            start_idx
        } else {
            match self.next_active(start_idx) {
                Some(s) => s,
                None => return Vec::new(),
            }
        };
        let mut order = vec![start];
        let mut idx = self.next_active(start);
        while let Some(i) = idx {
            if i == start {
                break;
            }
            order.push(i);
            idx = self.next_active(i);
        }
        order
    }

    pub fn begin_trick(&mut self, leader_idx: usize, first_trick: bool) -> Option<TrickState> {
        let leader_idx = self.ensure_leader_active(Some(leader_idx))?;
        let order = self.active_in_order(leader_idx);
        let colour = if first_trick { Some(2u8) } else { None }; // Spade
        self.trick_number += 1;
        self.info.sync_hands(&self.hands);
        Some(TrickState {
            leader_idx,
            first_trick,
            order,
            colour,
            stack: Vec::new(),
            highest_card: None,
            highest_idx: Some(leader_idx),
            seat_pos: 0,
            done: false,
            result: None,
            next_leader: None,
            thulla_by: None,
        })
    }

    pub fn expected_for_seat(&self, trick: &TrickState, seat_idx: usize) -> Option<Vec<Card>> {
        let i = trick.order.iter().position(|&s| s == seat_idx)?;
        if i != trick.seat_pos {
            return None;
        }
        if trick.first_trick {
            return if i == 0 {
                Some(vec![ACE_SPADES])
            } else {
                Some(cards_of_suit(2).to_vec())
            };
        }
        if i == 0 {
            return None;
        }
        trick.colour.map(|c| cards_of_suit(c).to_vec())
    }

    pub fn apply_play(&mut self, trick: &mut TrickState, seat_idx: usize, card: Card) -> &'static str {
        assert!(!trick.done);
        assert_eq!(trick.order[trick.seat_pos], seat_idx);

        let expected = self.expected_for_seat(trick, seat_idx);
        let hand = &self.hands[seat_idx];
        let moves = valid_moves(hand, expected.as_deref());
        assert!(
            moves.contains(&card),
            "illegal card {} for seat {}",
            card,
            seat_idx
        );
        let pos = self.hands[seat_idx]
            .iter()
            .position(|&c| c == card)
            .expect("card in hand");
        self.hands[seat_idx].remove(pos);

        let i = trick.seat_pos;
        let colour_before = trick.colour;
        trick.stack.push(card);
        self.info.note_play(seat_idx, card, colour_before);

        if i == 0 {
            trick.colour = Some(crate::card::suit(card));
            trick.highest_card = Some(card);
            trick.highest_idx = Some(seat_idx);
            trick.seat_pos += 1;
            if trick.seat_pos >= trick.order.len() {
                return self.finish_clean_trick(trick);
            }
            return "continue";
        }

        let led = trick.colour.unwrap();
        if crate::card::suit(card) != led {
            if trick.first_trick {
                trick.seat_pos += 1;
                if trick.seat_pos >= trick.order.len() {
                    return self.finish_clean_trick(trick);
                }
                return "continue";
            }
            let victim = trick.highest_idx.unwrap();
            let stack = trick.stack.clone();
            self.hands[victim].extend_from_slice(&stack);
            self.hands[victim].sort_by_key(|c| (crate::card::suit(*c), crate::card::rank(*c)));
            self.info.finish_thulla(victim, &stack);
            trick.done = true;
            trick.result = Some("thulla");
            trick.thulla_by = Some(seat_idx);
            trick.next_leader = Some(victim);
            return "thulla";
        }

        if card_gt(card, trick.highest_card.unwrap()) {
            trick.highest_card = Some(card);
            trick.highest_idx = Some(seat_idx);
        }
        trick.seat_pos += 1;
        if trick.seat_pos >= trick.order.len() {
            return self.finish_clean_trick(trick);
        }
        "continue"
    }

    fn finish_clean_trick(&mut self, trick: &mut TrickState) -> &'static str {
        self.info.finish_clean(&trick.stack);
        trick.done = true;
        trick.result = Some("trick_won");
        trick.next_leader = trick.highest_idx;
        "trick_won"
    }

    pub fn take_offer_context(&mut self, leader_idx: usize, taker_idx: usize) -> Option<(usize, usize)> {
        let leader_idx = self.ensure_leader_active(Some(leader_idx))?;
        if self.active_player_indices.len() <= 2 {
            return None;
        }
        if !self.active_player_indices.contains(&taker_idx) {
            return None;
        }
        let target = self.next_active(taker_idx)?;
        if target == taker_idx {
            return None;
        }
        let n = self.hands[target].len();
        self.info.sync_hands(&self.hands);
        let _ = leader_idx;
        Some((target, n))
    }

    pub fn apply_take(&mut self, leader_idx: usize, taker_idx: usize, accept: bool) -> Option<usize> {
        let ctx = self.take_offer_context(leader_idx, taker_idx);
        let Some((target, _n)) = ctx else {
            return self.ensure_leader_active(Some(leader_idx));
        };
        if !accept {
            return self.ensure_leader_active(Some(leader_idx));
        }
        let cards = std::mem::take(&mut self.hands[target]);
        self.info.note_take(taker_idx, target, &cards);
        self.hands[taker_idx].extend_from_slice(&cards);
        self.hands[taker_idx].sort_by_key(|c| (crate::card::suit(*c), crate::card::rank(*c)));
        self.info.sync_hands(&self.hands);
        self.record_got_away(target);
        self.ensure_leader_active(Some(leader_idx))
    }

    pub fn check_got_away(&mut self, from_idx: usize) -> Option<usize> {
        let emptied: Vec<usize> = self
            .active_in_order(from_idx)
            .into_iter()
            .filter(|&idx| self.hands[idx].is_empty())
            .collect();
        for idx in emptied {
            self.record_got_away(idx);
        }
        self.ensure_leader_active(Some(from_idx))
    }

    pub fn record_got_away(&mut self, idx: usize) {
        if !self.active_player_indices.contains(&idx) {
            return;
        }
        self.winners.push(idx);
        self.active_player_indices.retain(|&x| x != idx);
        self.info.note_got_away(idx);
    }

    pub fn view_remaining_after(&self, trick: &TrickState, seat_idx: usize) -> Vec<usize> {
        let i = trick.order.iter().position(|&s| s == seat_idx).unwrap();
        trick.order[i + 1..].to_vec()
    }
}
