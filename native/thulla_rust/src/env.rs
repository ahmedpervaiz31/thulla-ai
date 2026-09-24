//! DMC self-play env mirroring thulla_dmc.env.ThullaEnv (4 seats).

use crate::card::{valid_moves, Card, NUM_PLAYERS, TAKE_ASK_IDX, TAKE_PASS_IDX};
use crate::encode::{build_action_batch, encode_state, ActionEnc};
use crate::game::{Game, TrickState};
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rand::seq::SliceRandom;

pub const FINISH_REWARDS: [f32; 4] = [2.0, 1.5, 1.0, -1.0];

#[derive(Clone, Debug)]
pub struct Env {
    pub game: Game,
    pub trick: Option<TrickState>,
    pub leader: Option<usize>,
    pub play_history: Vec<Card>,
    pub phase: Phase,
    take_queue: Vec<usize>,
    take_pos: usize,
    take_leader: Option<usize>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Play,
    Take,
}

#[derive(Clone, Debug)]
pub struct Obs {
    pub position: usize,
    pub phase: Phase,
    pub legal: Vec<ActionEnc>,
    pub x_no: Vec<f32>,
    pub z_flat: Vec<f32>,
    pub x_batch: Vec<f32>,
    pub z_batch: Vec<f32>,
}

impl Env {
    pub fn new() -> Self {
        Self {
            game: Game::new(NUM_PLAYERS),
            trick: None,
            leader: None,
            play_history: Vec::new(),
            phase: Phase::Play,
            take_queue: Vec::new(),
            take_pos: 0,
            take_leader: None,
        }
    }

    pub fn reset_with_seed(&mut self, seed: u64) -> Obs {
        let mut rng = ChaCha8Rng::seed_from_u64(seed);
        let mut deck: Vec<Card> = (0..52u8).collect();
        deck.shuffle(&mut rng);
        self.game.deal_from_deck(&deck);
        self.play_history.clear();
        self.phase = Phase::Play;
        self.take_queue.clear();
        self.take_pos = 0;
        self.take_leader = None;
        self.leader = Some(self.game.ace_spades_holder_idx);
        self.trick = self.game.begin_trick(self.leader.unwrap(), true);
        self.obs_for_current()
    }

    pub fn reset_with_hands(&mut self, hands: Vec<Vec<Card>>, ace_holder: usize) -> Obs {
        self.game.set_hands(hands, Some(ace_holder));
        self.play_history.clear();
        self.phase = Phase::Play;
        self.take_queue.clear();
        self.take_pos = 0;
        self.take_leader = None;
        self.leader = Some(ace_holder);
        self.trick = self.game.begin_trick(ace_holder, true);
        self.obs_for_current()
    }

    pub fn current_seat(&self) -> usize {
        match self.phase {
            Phase::Take => self.take_queue[self.take_pos],
            Phase::Play => {
                let t = self.trick.as_ref().unwrap();
                t.order[t.seat_pos]
            }
        }
    }

    pub fn legal_actions(&self) -> Vec<ActionEnc> {
        match self.phase {
            Phase::Take => vec![ActionEnc::Ask, ActionEnc::Pass],
            Phase::Play => {
                let seat = self.current_seat();
                let trick = self.trick.as_ref().unwrap();
                let expected = self.game.expected_for_seat(trick, seat);
                valid_moves(&self.game.hands[seat], expected.as_deref())
                    .into_iter()
                    .map(ActionEnc::Card)
                    .collect()
            }
        }
    }

    pub fn obs_for_current(&self) -> Obs {
        let seat = self.current_seat();
        let legal = self.legal_actions();
        let take = self.phase == Phase::Take;
        let i_am_leader = take && Some(seat) == self.take_leader;
        let trick_ref = if take { None } else { self.trick.as_ref() };
        let (x_no, z_flat) = encode_state(
            &self.game,
            seat,
            trick_ref,
            &self.play_history,
            take,
            i_am_leader,
        );
        let (x_batch, z_batch) = build_action_batch(&x_no, &z_flat, &legal);
        Obs {
            position: seat,
            phase: self.phase,
            legal,
            x_no,
            z_flat,
            x_batch,
            z_batch,
        }
    }

    /// Step with action encoding: card index 0..51, or 52=ASK, 53=PASS.
    pub fn step(&mut self, action_code: usize) -> (Option<Obs>, [f32; 4], bool) {
        match self.phase {
            Phase::Take => self.step_take(action_code),
            Phase::Play => self.step_play(action_code),
        }
    }

    fn step_play(&mut self, action_code: usize) -> (Option<Obs>, [f32; 4], bool) {
        assert!(action_code < 52);
        let card = action_code as Card;
        let seat = self.current_seat();
        let legal = self.legal_actions();
        assert!(
            legal.contains(&ActionEnc::Card(card)),
            "illegal action {}",
            action_code
        );
        let trick = self.trick.as_mut().unwrap();
        self.game.apply_play(trick, seat, card);
        self.play_history.push(card);

        let zero = [0.0f32; 4];
        if !self.trick.as_ref().unwrap().done {
            return (Some(self.obs_for_current()), zero, false);
        }
        let next_leader = self.trick.as_ref().unwrap().next_leader;
        let next_leader = self.game.check_got_away(next_leader.unwrap_or(seat));
        if self.is_finished(next_leader) {
            return self.terminal();
        }
        self.begin_take_phase(next_leader.unwrap())
    }

    fn step_take(&mut self, action_code: usize) -> (Option<Obs>, [f32; 4], bool) {
        let accept = action_code == TAKE_ASK_IDX;
        assert!(action_code == TAKE_ASK_IDX || action_code == TAKE_PASS_IDX);
        let seat = self.current_seat();
        let leader = self.take_leader.unwrap();
        self.leader = self.game.apply_take(leader, seat, accept);
        let zero = [0.0f32; 4];
        if self.is_finished(self.leader) {
            return self.terminal();
        }
        self.take_pos += 1;
        self.advance_take_queue();
        if self.take_pos >= self.take_queue.len() {
            return self.start_next_trick();
        }
        (Some(self.obs_for_current()), zero, false)
    }

    fn begin_take_phase(&mut self, leader_idx: usize) -> (Option<Obs>, [f32; 4], bool) {
        let leader_idx = self.game.ensure_leader_active(Some(leader_idx));
        if leader_idx.is_none() || self.game.active_player_indices.len() <= 2 {
            self.leader = leader_idx;
            return self.start_next_trick();
        }
        let leader_idx = leader_idx.unwrap();
        self.phase = Phase::Take;
        self.take_leader = Some(leader_idx);
        self.leader = Some(leader_idx);
        self.trick = None;
        self.game.info.sync_hands(&self.game.hands);
        self.take_queue = self
            .game
            .active_in_order(leader_idx)
            .into_iter()
            .filter(|&idx| self.game.take_offer_context(leader_idx, idx).is_some())
            .collect();
        self.take_pos = 0;
        if self.take_queue.is_empty() {
            return self.start_next_trick();
        }
        (Some(self.obs_for_current()), [0.0; 4], false)
    }

    fn advance_take_queue(&mut self) {
        let leader = self.take_leader.unwrap();
        while self.take_pos < self.take_queue.len() {
            let seat = self.take_queue[self.take_pos];
            if self.game.take_offer_context(leader, seat).is_none() {
                self.take_pos += 1;
                continue;
            }
            if self.game.active_player_indices.len() <= 2 {
                self.take_pos = self.take_queue.len();
                return;
            }
            break;
        }
    }

    fn start_next_trick(&mut self) -> (Option<Obs>, [f32; 4], bool) {
        let leader = self.game.ensure_leader_active(self.leader);
        if self.is_finished(leader) {
            return self.terminal();
        }
        self.phase = Phase::Play;
        self.take_queue.clear();
        self.take_pos = 0;
        self.take_leader = None;
        self.leader = leader;
        self.trick = self.game.begin_trick(leader.unwrap(), false);
        if self.trick.is_none() || self.is_finished(self.leader) {
            return self.terminal();
        }
        (Some(self.obs_for_current()), [0.0; 4], false)
    }

    fn is_finished(&self, leader: Option<usize>) -> bool {
        leader.is_none() || self.game.active_player_indices.len() <= 1
    }

    fn terminal(&mut self) -> (Option<Obs>, [f32; 4], bool) {
        (None, self.finish_rewards(), true)
    }

    pub fn finish_rewards(&self) -> [f32; 4] {
        let mut order = self.game.winners.clone();
        for &idx in &self.game.active_player_indices {
            if !order.contains(&idx) {
                order.push(idx);
            }
        }
        for i in 0..NUM_PLAYERS {
            if !order.contains(&i) {
                order.push(i);
            }
        }
        order.truncate(NUM_PLAYERS);
        let mut rewards = [0.0f32; 4];
        for (place, &seat) in order.iter().enumerate() {
            rewards[seat] = FINISH_REWARDS[place.min(FINISH_REWARDS.len() - 1)];
        }
        rewards
    }
}

impl Default for Env {
    fn default() -> Self {
        Self::new()
    }
}
