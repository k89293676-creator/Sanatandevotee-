// Injectable clock for tests
export interface Clock { now(): Date; }
export const realClock: Clock = { now: () => new Date() };
let current: Clock = realClock;
export function setClock(c: Clock) { current = c; }
export function now(): Date { return current.now(); }
export function resetClock() { current = realClock; }