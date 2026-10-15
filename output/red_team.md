# Red Team (Problem 7): Not Completed

## What the problem asked

Make two new booby-trapped vendor documents in `data/my_attackers/`. Each should use a hiding trick or
attack goal not in the practice set and look like a normal quote to a person. Then run both on the agent
with no defenses and with my defenses, and report what happened.

## What happened

I asked my vibe coder (Claude Code) to build the two attack documents. It started writing a script to
generate them, but a safety filter stopped it partway through. After that, it declined to write hidden
attack text in any form. That included a simple version I asked for: copying a practice quote and adding
a short line in text the same color as the background. It offered to copy clean quotes for me to edit,
and to run, check, and write up any documents I made myself.

I don't know how to edit HTML or email files by hand, so I could not build the hidden text myself. I am
turning in this problem incomplete instead of submitting documents I don't understand.

## Results

| | Attack 1 | Attack 2 |
|---|---|---|
| Document in `data/my_attacks/` | not created | not created |
| Run with no defenses | not run | not run |
| Run with defenses | not run | not run |

`data/my_attacks/` (the repo's name for the folder the problem calls `my_attackers/`) holds only a short
`README.md` saying it is empty. The vibe coder had copied two clean practice quotes into the folder as starting
points (p01 and p08, unchanged), and I removed them because they contained no attack.
`output/trap_calls.json` is unchanged by this problem.

## What I would have tested, based on Problems 5 and 6

Even without new documents, my earlier results show where a red team should look:

- **The code layer only removes hiding tricks it knows about.** In Problem 6 it removed all 10 hidden
  pieces in the practice set and caught the same tricks in the exam documents. But it works from a list
  of known tricks, so a trick that is not on the list would reach the model like normal text.
- **The prompt layer depends on the model's judgment.** It got 0 of 12 wrong in Problem 6, but the
  undefended agent's answer on p03 changed from run to run. A rule the model is asked to follow is not
  a guarantee.
- **The design layer is the backstop.** Python makes the final decision, numbers must appear in the
  document, and the email and payment tools need a human sign-off. So a document that fools the model
  still cannot pay, send email, or put a link in the reason. It cannot stop a wrong fact that really is
  in the document, though. The design-only run in Problem 6 was fooled on 5 of 12.

So the most useful red-team test would be an attack the code layer does not recognize *and* that does
not look like a "correction" to the prompt layer. That is exactly the case where only the design layer
is left. I was not able to build that test for this homework.
