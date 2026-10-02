INSERT INTO quizzes(category,question,option_a,option_b,option_c,option_d,correct_answer,age_group) VALUES
('Digital Safety','Who should know your LittleNet password?','Your best friend','Only your parent or guardian','Anyone in chat','A player offering free prizes','Only your parent or guardian','6-8'),
('Digital Safety','A stranger online asks for your home address. What do you do?','Share it quickly','Never share it, and tell a parent','Share a fake address','Ask them for their address','Never share it, and tell a parent','6-8'),
('Kindness','Someone writes a mean comment on your drawing. What do you do?','Write a meaner comment back','Tell a parent, and block or report them','Delete your whole profile','Share their phone number','Tell a parent, and block or report them','6-8'),
('Kindness','You see someone being teased in a group chat. What is the kind thing to do?','Laugh along','Stand up for them or tell an adult','Forward the chat to everyone','Stay silent','Stand up for them or tell an adult','6-8'),
('Stranger Safety','Someone you never met sends a friend request. What do you do?','Accept right away','Ask a parent first','Chat for a week, then decide','Share your photo first','Ask a parent first','6-8'),
('Stranger Safety','A stranger asks you to keep your chat a secret from your parents. What do you do?','Keep the secret','Tell a parent right away','Block your parents instead','Send more secrets','Tell a parent right away','6-8'),
('Healthy Habits','Your eyes feel tired after a long time on the screen. What should you do?','Keep scrolling','Take a break','Turn up the brightness','Watch faster videos','Take a break','6-8'),
('Healthy Habits','It is bedtime but you want to keep chatting. What should you do?','Chat all night','Go to sleep and chat tomorrow','Hide under the blanket and chat','Set an alarm for 3am','Go to sleep and chat tomorrow','6-8'),
('Digital Safety','Before you post a photo of your friend, what should you do?','Post it right away','Ask your friend first','Tag their whole family','Hide it from teachers','Ask your friend first','9-11'),
('Digital Safety','A game message says "free prizes if you share your password". What should you do?','Share it and get prizes','Never share it. It is a trick.','Share a friend''s password','Reply with your birthday','Never share it. It is a trick.','9-11'),
('Kindness','Is it okay to forward a mean rumor about a classmate?','Yes, if you did not start it','No. Never forward mean messages.','Yes, if you say sorry after','Only in secret chats','No. Never forward mean messages.','9-11'),
('Kindness','Your friend shared art you do not like. What is the kind choice?','Say it is ugly','Say something kind, or just scroll past','Tell others not to like it','Post a laughing emoji','Say something kind, or just scroll past','9-11'),
('Stranger Safety','Someone online asks for your photo. What do you do?','Send one quickly','Say no and tell a parent','Send a friend''s photo','Ask for theirs first','Say no and tell a parent','9-11'),
('Stranger Safety','A message from a stranger says "You won a prize! Click here." What do you do?','Click fast before it ends','Do not click. Tell a parent.','Forward it to friends','Reply with your name','Do not click. Tell a parent.','9-11'),
('Healthy Habits','You feel sad after seeing something online. What should you do?','Keep it to yourself','Tell a parent about it','Watch more of it','Delete the app forever','Tell a parent about it','9-11'),
('Healthy Habits','A parent says screen time is over. What do you do?','Keep playing secretly','Stop and do something else','Argue for one more hour','Hide the phone','Stop and do something else','9-11'),
('Digital Safety','Should you share your school name with people you do not know online?','Yes, it is fun','No, keep it private','Only on weekends','Only if they share first','No, keep it private','12-13'),
('Digital Safety','You used a school computer to log in. What do you do before leaving?','Just walk away','Log out','Save the password','Leave the page open','Log out','12-13'),
('Kindness','A friend wants to leave someone out of a group. What do you say?','Agree to stay popular','Let''s include everyone','Leave the group','Start a vote about them','Let''s include everyone','12-13'),
('Kindness','Before you post a comment, what should you ask yourself?','Will this get many likes?','Is it kind and true?','Is it funny enough?','Will it shock people?','Is it kind and true?','12-13'),
('Stranger Safety','Is it safe to meet in real life someone you only know online?','Yes, if they seem nice','No. Never go without a parent.','Yes, if you bring a friend','Yes, in the daytime','No. Never go without a parent.','12-13'),
('Stranger Safety','A new online friend asks which park you play at. What do you say?','Tell them the park name','Do not share it. Tell a parent.','Meet them there tomorrow','Send a map pin','Do not share it. Tell a parent.','12-13'),
('Healthy Habits','You see something scary in a video. What should you do?','Keep watching','Close it and tell a parent','Share it with friends','Watch it again','Close it and tell a parent','12-13'),
('Healthy Habits','You get a message threatening to share a private photo. What do you do first?','Do what they say','Save it as proof and tell a trusted adult','Reply with anger','Delete everything','Save it as proof and tell a trusted adult','12-13')
ON CONFLICT DO NOTHING;

INSERT INTO learning_challenges(title,description,challenge_type,prompt,expected_answer,age_group,points) VALUES
('Password Detective','Choose the strongest password idea.','CYBER_SAFETY','Which is safer: puppy123 or R7!mQ2#z?','R7!mQ2#z','6-8',10),
('Kind Comment Challenge','Practice writing a positive online response.','ACTIVITY','Write one kind sentence you could post for a friend.',NULL,'6-8',10),
('Spot the Phishing Clue','Think before you click unknown links.','CYBER_SAFETY','Should you open a prize link sent by a stranger? Answer yes or no.','no','9-11',15),
('Math Sprint','Solve a short mental-math challenge.','PUZZLE','What is 18 x 5?','90','9-11',15),
('Privacy Check','Learn what should stay private online.','CYBER_SAFETY','Should your home address be posted publicly? Answer yes or no.','no','12-13',20),
('Logic Pattern','Complete the number pattern.','PUZZLE','2, 4, 8, 16, ?','32','12-13',20),
('Digital Footprint','Think about long-term online impact.','ACTIVITY','Write one thing you should check before posting online.',NULL,'14-18',20),
('Security Reasoning','Recognize safer account behaviour.','CYBER_SAFETY','Is reusing one password everywhere safe? Answer yes or no.','no','14-18',20)
ON CONFLICT DO NOTHING;
