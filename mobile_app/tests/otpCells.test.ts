import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  OTP_LENGTH,
  applyOtpBackspace,
  applyOtpInput,
  cellsFromCode,
  emptyOtpCells,
  isOtpComplete,
} from '../src/screens/otpCells';

describe('six-cell OTP input logic', () => {
  it('starts empty with six cells', () => {
    assert.equal(emptyOtpCells().length, OTP_LENGTH);
    assert.deepEqual(emptyOtpCells(), ['', '', '', '', '', '']);
  });

  it('builds cells from a dev code, digits only', () => {
    assert.deepEqual(cellsFromCode('482913'), ['4', '8', '2', '9', '1', '3']);
    assert.deepEqual(cellsFromCode('48a9 13!'), ['4', '8', '9', '1', '3', '']);
    assert.deepEqual(cellsFromCode(undefined), ['', '', '', '', '', '']);
  });

  it('typing one digit fills the cell and advances focus', () => {
    const { cells, focus } = applyOtpInput(emptyOtpCells(), 0, '4');
    assert.deepEqual(cells, ['4', '', '', '', '', '']);
    assert.equal(focus, 1);
  });

  it('pasting the full code distributes it across the cells', () => {
    const { cells, focus } = applyOtpInput(emptyOtpCells(), 0, '482913');
    assert.deepEqual(cells, ['4', '8', '2', '9', '1', '3']);
    assert.equal(focus, 5);
  });

  it('autofill into a middle cell distributes forward only', () => {
    const start = ['4', '8', '', '', '', ''];
    const { cells, focus } = applyOtpInput(start, 2, '2913');
    assert.deepEqual(cells, ['4', '8', '2', '9', '1', '3']);
    assert.equal(focus, 5);
  });

  it('backspace on an empty cell moves back and clears the previous cell', () => {
    const start = ['4', '8', '2', '', '', ''];
    const { cells, focus } = applyOtpBackspace(start, 3);
    assert.deepEqual(cells, ['4', '8', '', '', '', '']);
    assert.equal(focus, 2);
  });

  it('backspace on the first cell stays put', () => {
    const start = emptyOtpCells();
    const { cells, focus } = applyOtpBackspace(start, 0);
    assert.deepEqual(cells, start);
    assert.equal(focus, 0);
  });

  it('clearing a filled cell keeps focus on that cell', () => {
    const start = ['4', '8', '', '', '', ''];
    const { cells, focus } = applyOtpInput(start, 1, '');
    assert.deepEqual(cells, ['4', '', '', '', '', '']);
    assert.equal(focus, 1);
  });

  it('reports completeness only for six digits', () => {
    assert.equal(isOtpComplete(cellsFromCode('482913')), true);
    assert.equal(isOtpComplete(cellsFromCode('48291')), false);
    assert.equal(isOtpComplete(emptyOtpCells()), false);
  });
});
