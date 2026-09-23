-- migrate:up
-- Replace the 52-question jargon-heavy quiz bank with 24 short, simple,
-- scenario-based questions a 6-year-old can read. The 20260911230000 seed
-- migration is left untouched (it may already have run); this migration
-- deletes its rows by category and inserts the simplified bank idempotently.

DELETE FROM quizzes WHERE category IN (
  'Digital Privacy', 'Online Kindness', 'Cyber Smarts', 'Digital Well-being'
);

INSERT INTO quizzes(
  category, question, option_a, option_b, option_c, option_d,
  correct_answer, age_group, explanation
)
SELECT q.category, q.question, q.option_a, q.option_b, q.option_c, q.option_d,
       q.correct_answer, age.age_group, q.explanation
FROM (VALUES
  ('Digital Safety', 'Who should know your LittleNet password?', 'Your best friend', 'Only your parent or guardian', 'Anyone in chat', 'A player offering free prizes', 'Only your parent or guardian', 'Only a parent or guardian should ever know your password.'),
  ('Digital Safety', 'A stranger online asks for your home address. What do you do?', 'Share it quickly', 'Never share it, and tell a parent', 'Share a fake address', 'Ask them for their address', 'Never share it, and tell a parent', 'Your home address must stay private. Always tell a parent.'),
  ('Digital Safety', 'Before you post a photo of your friend, what should you do?', 'Post it right away', 'Ask your friend first', 'Tag their whole family', 'Hide it from teachers', 'Ask your friend first', 'Always ask before posting photos of other people.'),
  ('Digital Safety', 'A game message says "free prizes if you share your password". What should you do?', 'Share it and get prizes', 'Never share it. It is a trick.', 'Share a friend''s password', 'Reply with your birthday', 'Never share it. It is a trick.', 'Nobody real gives prizes for passwords. It is a trick to steal accounts.'),
  ('Digital Safety', 'Should you share your school name with people you do not know online?', 'Yes, it is fun', 'No, keep it private', 'Only on weekends', 'Only if they share first', 'No, keep it private', 'Your school name tells strangers where to find you. Keep it private.'),
  ('Digital Safety', 'You used a school computer to log in. What do you do before leaving?', 'Just walk away', 'Log out', 'Save the password', 'Leave the page open', 'Log out', 'Always log out on shared computers so others cannot open your account.'),
  
  ('Kindness', 'Someone writes a mean comment on your drawing. What do you do?', 'Write a meaner comment back', 'Tell a parent, and block or report them', 'Delete your whole profile', 'Share their phone number', 'Tell a parent, and block or report them', 'LittleNet has report and block tools to keep your space kind.'),
  ('Kindness', 'You see someone being teased in a group chat. What is the kind thing to do?', 'Laugh along', 'Stand up for them or tell an adult', 'Forward the chat to everyone', 'Stay silent', 'Stand up for them or tell an adult', 'Standing up for others makes LittleNet safe for everyone.'),
  ('Kindness', 'Is it okay to forward a mean rumor about a classmate?', 'Yes, if you did not start it', 'No. Never forward mean messages.', 'Yes, if you say sorry after', 'Only in secret chats', 'No. Never forward mean messages.', 'Forwarding rumors hurts people. Break the chain.'),
  ('Kindness', 'Your friend shared art you do not like. What is the kind choice?', 'Say it is ugly', 'Say something kind, or just scroll past', 'Tell others not to like it', 'Post a laughing emoji', 'Say something kind, or just scroll past', 'Kind words make creators happy. You can always scroll past.'),
  ('Kindness', 'A friend wants to leave someone out of a group. What do you say?', 'Agree to stay popular', 'Let''s include everyone', 'Leave the group', 'Start a vote about them', 'Let''s include everyone', 'Including everyone keeps groups fun and safe.'),
  ('Kindness', 'Before you post a comment, what should you ask yourself?', 'Will this get many likes?', 'Is it kind and true?', 'Is it funny enough?', 'Will it shock people?', 'Is it kind and true?', 'Five seconds of thinking stops posts you might regret.'),
  
  ('Stranger Safety', 'Someone you never met sends a friend request. What do you do?', 'Accept right away', 'Ask a parent first', 'Chat for a week, then decide', 'Share your photo first', 'Ask a parent first', 'Only connect with people a parent says are okay.'),
  ('Stranger Safety', 'A stranger asks you to keep your chat a secret from your parents. What do you do?', 'Keep the secret', 'Tell a parent right away', 'Block your parents instead', 'Send more secrets', 'Tell a parent right away', 'Anyone who asks for secrecy is unsafe. Tell a parent immediately.'),
  ('Stranger Safety', 'Someone online asks for your photo. What do you do?', 'Send one quickly', 'Say no and tell a parent', 'Send a friend''s photo', 'Ask for theirs first', 'Say no and tell a parent', 'Never send photos to strangers. Tell a parent.'),
  ('Stranger Safety', 'A message from a stranger says "You won a prize! Click here." What do you do?', 'Click fast before it ends', 'Do not click. Tell a parent.', 'Forward it to friends', 'Reply with your name', 'Do not click. Tell a parent.', 'Prize messages from strangers are tricks. Do not click.'),
  ('Stranger Safety', 'Is it safe to meet in real life someone you only know online?', 'Yes, if they seem nice', 'No. Never go without a parent.', 'Yes, if you bring a friend', 'Yes, in the daytime', 'No. Never go without a parent.', 'People online may not be who they say. Never meet them.'),
  ('Stranger Safety', 'A new online friend asks which park you play at. What do you say?', 'Tell them the park name', 'Do not share it. Tell a parent.', 'Meet them there tomorrow', 'Send a map pin', 'Do not share it. Tell a parent.', 'Never share places you go. Tell a parent.'),
  
  ('Healthy Habits', 'Your eyes feel tired after a long time on the screen. What should you do?', 'Keep scrolling', 'Take a break', 'Turn up the brightness', 'Watch faster videos', 'Take a break', 'Tired eyes mean your body needs a break.'),
  ('Healthy Habits', 'It is bedtime but you want to keep chatting. What should you do?', 'Chat all night', 'Go to sleep and chat tomorrow', 'Hide under the blanket and chat', 'Set an alarm for 3am', 'Go to sleep and chat tomorrow', 'Sleep keeps your brain strong. Chats can wait.'),
  ('Healthy Habits', 'You feel sad after seeing something online. What should you do?', 'Keep it to yourself', 'Tell a parent about it', 'Watch more of it', 'Delete the app forever', 'Tell a parent about it', 'Talking to a parent always helps when something online upsets you.'),
  ('Healthy Habits', 'A parent says screen time is over. What do you do?', 'Keep playing secretly', 'Stop and do something else', 'Argue for one more hour', 'Hide the phone', 'Stop and do something else', 'Parents set limits to keep you healthy. There is always tomorrow.'),
  ('Healthy Habits', 'You see something scary in a video. What should you do?', 'Keep watching', 'Close it and tell a parent', 'Share it with friends', 'Watch it again', 'Close it and tell a parent', 'Close scary things right away and tell a parent.'),
  ('Healthy Habits', 'You get a message threatening to share a private photo. What do you do first?', 'Do what they say', 'Save it as proof and tell a trusted adult', 'Reply with anger', 'Delete everything', 'Save it as proof and tell a trusted adult', 'Save the message and tell a trusted adult. They will handle it.')
  CROSS JOIN (VALUES ('6-8'), ('9-11'), ('12-13'), ('14-18')) AS age(age_group)
  ON CONFLICT (question, age_group) DO NOTHING;
) AS q(category, question, option_a, option_b, option_c, option_d, correct_answer, explanation)
CROSS JOIN (VALUES ('6-8'), ('9-11'), ('12-13'), ('14-18')) AS age(age_group)
ON CONFLICT (question, age_group) DO NOTHING;

-- migrate:down
-- Rollback removes the simplified bank this migration inserted. The older
-- 52-question bank deleted by the up migration is intentionally not restored:
-- it was superseded by design (quiz untwist, 2026-09-23).
DELETE FROM quizzes WHERE category IN (
  'Digital Safety', 'Kindness', 'Stranger Safety', 'Healthy Habits'
);
