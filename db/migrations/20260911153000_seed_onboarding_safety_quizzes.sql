-- migrate:up
-- Every supported child age band needs two real, FK-backed onboarding rows.
INSERT INTO quizzes(
  category, question, option_a, option_b, option_c, option_d,
  correct_answer, age_group, explanation
)
SELECT q.category, q.question, q.option_a, q.option_b, q.option_c, q.option_d,
       q.correct_answer, age.age_group, q.explanation
FROM (VALUES
  (
    'Digital Safety',
    'What should you do if someone you do not know asks for personal information online?',
    'Never share it and tell a trusted adult',
    'Send it if they seem friendly',
    'Post it in a public comment',
    'Share your school name instead',
    'Never share it and tell a trusted adult',
    'Personal details such as your address, phone number, and school must stay private.'
  ),
  (
    'Kindness Online',
    'How should we treat friends and classmates in comments and chats?',
    'With kindness, respect, and encouragement',
    'By posting mean jokes',
    'By sending hurtful messages',
    'By ignoring their feelings',
    'With kindness, respect, and encouragement',
    'Kind and respectful messages help keep LittleNet safe for everyone.'
  )
) AS q(
  category, question, option_a, option_b, option_c, option_d,
  correct_answer, explanation
)
CROSS JOIN (VALUES ('6-8'), ('9-11'), ('12-13'), ('14-18')) AS age(age_group)
ON CONFLICT (question, age_group) DO NOTHING;

-- migrate:down
DELETE FROM quizzes
WHERE question IN (
  'What should you do if someone you do not know asks for personal information online?',
  'How should we treat friends and classmates in comments and chats?'
)
AND age_group IN ('6-8', '9-11', '12-13', '14-18');
