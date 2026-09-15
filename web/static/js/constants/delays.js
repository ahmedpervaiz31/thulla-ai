/** Client-side pacing delays (ms) for auto / human CPU steps. */

/**
 * Target wall-clock for a CPU *card play* (server think + pad).
 * Fast decisions wait out the remainder so plays feel even; slow ones
 * are not padded further.
 */
export const DELAY_PLAY_TARGET = 900;
/** Clean trick win — pot hold before clearing. */
export const DELAY_REVEAL = 1100;
/** Thulla reveal — slightly longer so the dump lands. */
export const DELAY_REVEAL_THULLA = 1450;
/** Take / give consent auto-step (unchanged; not padded to play target). */
export const DELAY_TAKE = 320;
/** Floor after crediting server think time (take / reveal only). */
export const DELAY_MIN = 100;
