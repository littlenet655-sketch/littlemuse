"""Seed 200+ curated quiz questions into the quizzes table.
Run: python tools/seed_quizzes.py
Safe to run multiple times — uses ON CONFLICT DO NOTHING.
"""
from pathlib import Path
import sys
root = Path(__file__).parents[1]
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / '.env')
from database.connection import get_db_connection

QUESTIONS = [
    # ── 6-8 SCIENCE ─────────────────────────────────────────────────────────
    ('Science','Which planet is closest to the Sun?','Mercury','Venus','Earth','Mars','Mercury','6-8'),
    ('Science','How many legs does a spider have?','4','6','8','10','8','6-8'),
    ('Science','What do caterpillars turn into?','Bees','Butterflies','Moths','Dragonflies','Butterflies','6-8'),
    ('Science','Which animal is the fastest on land?','Lion','Horse','Cheetah','Leopard','Cheetah','6-8'),
    ('Science','What is the largest ocean on Earth?','Atlantic','Indian','Arctic','Pacific','Pacific','6-8'),
    ('Science','What colour is a healthy leaf?','Yellow','Brown','Green','Purple','Green','6-8'),
    ('Science','How many bones are in the human body?','106','206','306','406','206','6-8'),
    ('Science','Which sense do we use to taste food?','Sight','Touch','Taste','Hearing','Taste','6-8'),
    ('Science','What do bees produce?','Milk','Honey','Butter','Wax only','Honey','6-8'),
    ('Science','The Sun is a?','Planet','Moon','Star','Asteroid','Star','6-8'),
    # ── 6-8 MATH ────────────────────────────────────────────────────────────
    ('Math','What is 7 × 8?','54','56','64','48','56','6-8'),
    ('Math','How many minutes are in one hour?','30','45','60','100','60','6-8'),
    ('Math','What comes next? 2, 4, 6, 8, __','9','10','12','11','10','6-8'),
    ('Math','What is half of 20?','5','8','10','15','10','6-8'),
    ('Math','How many sides does a triangle have?','2','3','4','5','3','6-8'),
    ('Math','What is 100 - 37?','63','53','73','43','63','6-8'),
    ('Math','Which number is even?','3','7','9','12','12','6-8'),
    ('Math','What is 5 + 5 + 5?','10','20','15','25','15','6-8'),
    # ── 6-8 GENERAL KNOWLEDGE ───────────────────────────────────────────────
    ('General Knowledge','What is the capital of India?','Mumbai','Kolkata','New Delhi','Chennai','New Delhi','6-8'),
    ('General Knowledge','How many days are in a week?','5','6','7','8','7','6-8'),
    ('General Knowledge','Which festival is called the festival of lights?','Holi','Diwali','Eid','Christmas','Diwali','6-8'),
    ('General Knowledge','What animal says "moo"?','Sheep','Horse','Cow','Pig','Cow','6-8'),
    ('General Knowledge','How many colours are in a rainbow?','5','6','7','8','7','6-8'),
    ('General Knowledge','Which is the national bird of India?','Sparrow','Eagle','Peacock','Parrot','Peacock','6-8'),
    ('General Knowledge','What is the colour of the sky on a clear day?','Green','Red','Blue','Yellow','Blue','6-8'),
    ('General Knowledge','How many months are in a year?','10','11','12','13','12','6-8'),
    # ── 6-8 RIDDLES ─────────────────────────────────────────────────────────
    ('Riddle','I have hands but cannot clap. What am I?','Robot','Clock','Puppet','Scarecrow','Clock','6-8'),
    ('Riddle','I am full of holes but still holds water. What am I?','Net','Sponge','Bucket','Jar','Sponge','6-8'),
    ('Riddle','What gets wetter the more it dries?','Towel','Soap','Water','Sand','Towel','6-8'),
    ('Riddle','I have a tail and a head but no body. What am I?','Snake','Coin','Arrow','Needle','Coin','6-8'),
    ('Riddle','What has teeth but cannot bite?','Dog','Comb','Saw','Fork','Comb','6-8'),
    # ── 6-8 EMOJI QUIZ ──────────────────────────────────────────────────────
    ('Emoji Quiz','🌊🐟 — Where do fish live?','Desert','Mountain','Ocean','Sky','Ocean','6-8'),
    ('Emoji Quiz','🌙⭐ — When do you see stars?','Morning','Afternoon','Night','Noon','Night','6-8'),
    ('Emoji Quiz','🍎🌳 — Where do apples grow?','Underground','On trees','In water','In sand','On trees','6-8'),

    # ── 9-11 SCIENCE ────────────────────────────────────────────────────────
    ('Science','What is the chemical symbol for water?','WA','HO','H2O','W2O','H2O','9-11'),
    ('Science','How many planets are in our solar system?','7','8','9','10','8','9-11'),
    ('Science','What is the powerhouse of the cell?','Nucleus','Mitochondria','Ribosome','Vacuole','Mitochondria','9-11'),
    ('Science','Which gas do humans breathe out?','Oxygen','Nitrogen','Carbon dioxide','Hydrogen','Carbon dioxide','9-11'),
    ('Science','What is the speed of light (approx)?','3 lakh km/s','1 lakh km/s','5 lakh km/s','9 lakh km/s','3 lakh km/s','9-11'),
    ('Science','What type of animal is a dolphin?','Fish','Reptile','Mammal','Amphibian','Mammal','9-11'),
    ('Science','Which planet has rings around it?','Mars','Jupiter','Saturn','Uranus','Saturn','9-11'),
    ('Science','What is the boiling point of water?','50°C','75°C','100°C','120°C','100°C','9-11'),
    ('Science','Sound travels fastest through?','Air','Vacuum','Water','Steel','Steel','9-11'),
    ('Science','Photosynthesis happens in which part of a plant?','Roots','Stem','Leaves','Flowers','Leaves','9-11'),
    ('Science','What force pulls objects toward Earth?','Magnetism','Friction','Gravity','Tension','Gravity','9-11'),
    # ── 9-11 MATH ────────────────────────────────────────────────────────────
    ('Math','What is the square root of 144?','11','12','13','14','12','9-11'),
    ('Math','What is 15% of 200?','20','25','30','35','30','9-11'),
    ('Math','If a triangle has angles 60°, 60°, what is the third angle?','30°','60°','90°','120°','60°','9-11'),
    ('Math','What is the perimeter of a square with side 7cm?','21cm','28cm','14cm','49cm','28cm','9-11'),
    ('Math','What is 2³ (2 to the power 3)?','6','8','9','12','8','9-11'),
    ('Math','A train travels 60 km/h. How far in 3 hours?','120km','150km','180km','200km','180km','9-11'),
    ('Math','What is the LCM of 4 and 6?','8','10','12','24','12','9-11'),
    ('Math','What comes next? 1, 1, 2, 3, 5, 8, __','11','12','13','14','13','9-11'),
    # ── 9-11 GENERAL KNOWLEDGE ───────────────────────────────────────────────
    ('General Knowledge','Who wrote the national anthem of India?','Bankim Chandra','Rabindranath Tagore','Mahatma Gandhi','Sarojini Naidu','Rabindranath Tagore','9-11'),
    ('General Knowledge','Mount Everest is in which country?','India','China','Nepal','Tibet','Nepal','9-11'),
    ('General Knowledge','What is the largest continent?','Africa','Europe','Asia','Australia','Asia','9-11'),
    ('General Knowledge','The Taj Mahal is located in?','Delhi','Agra','Jaipur','Lucknow','Agra','9-11'),
    ('General Knowledge','Which sport uses a shuttlecock?','Tennis','Badminton','Cricket','Hockey','Badminton','9-11'),
    ('General Knowledge','How many players are in a cricket team?','9','10','11','12','11','9-11'),
    ('General Knowledge','The Indian currency is called?','Dollar','Rupee','Pound','Euro','Rupee','9-11'),
    ('General Knowledge','Which day is celebrated as Independence Day in India?','26 Jan','15 Aug','2 Oct','14 Nov','15 Aug','9-11'),
    ('General Knowledge','Who invented the telephone?','Edison','Tesla','Bell','Marconi','Bell','9-11'),
    # ── 9-11 RIDDLES ─────────────────────────────────────────────────────────
    ('Riddle','The more you take, the more you leave behind. What am I?','Time','Footsteps','Memories','Shadows','Footsteps','9-11'),
    ('Riddle','I speak without a mouth and hear without ears. What am I?','Echo','Radio','Wind','Mirror','Echo','9-11'),
    ('Riddle','What has cities but no houses, mountains but no trees?','A dream','A map','A picture','A globe','A map','9-11'),
    ('Riddle','I can fly without wings. What am I?','Cloud','Time','Dream','Thought','Time','9-11'),
    # ── 9-11 EMOJI QUIZ ──────────────────────────────────────────────────────
    ('Emoji Quiz','🧲 attracts which material?','Wood','Plastic','Iron','Glass','Iron','9-11'),
    ('Emoji Quiz','🌍 rotates around ☀️ in how many days?','265','365','465','565','365','9-11'),
    ('Emoji Quiz','🏏 + 🇮🇳 — India national sport is?','Hockey','Cricket','Football','Kabaddi','Hockey','9-11'),

    # ── 12-13 SCIENCE ────────────────────────────────────────────────────────
    ('Science','What is the atomic number of Carbon?','4','6','8','12','6','12-13'),
    ('Science','DNA stands for?','Dioxyribose Nucleic Acid','Deoxyribonucleic Acid','Double Nuclear Acid','Dynamic Nuclear Atom','Deoxyribonucleic Acid','12-13'),
    ('Science','Which layer of Earth\'s atmosphere blocks UV rays?','Troposphere','Mesosphere','Ozone layer','Ionosphere','Ozone layer','12-13'),
    ('Science','Newton\'s second law: F = ?','ma','mv','m/a','mg','ma','12-13'),
    ('Science','What is the SI unit of electric current?','Volt','Ohm','Ampere','Watt','Ampere','12-13'),
    ('Science','Which blood type is universal donor?','A+','B-','AB+','O-','O-','12-13'),
    ('Science','What is the process of cell division called?','Osmosis','Mitosis','Photosynthesis','Diffusion','Mitosis','12-13'),
    ('Science','Sound cannot travel through?','Water','Air','Vacuum','Steel','Vacuum','12-13'),
    ('Science','The pH of pure water is?','5','7','9','10','7','12-13'),
    ('Science','Which part of the brain controls balance?','Cerebrum','Cerebellum','Medulla','Hypothalamus','Cerebellum','12-13'),
    # ── 12-13 MATH ────────────────────────────────────────────────────────────
    ('Math','What is the value of π (pi) approximately?','2.14','3.14','4.14','5.14','3.14','12-13'),
    ('Math','Solve: 3x + 7 = 22. x = ?','4','5','6','7','5','12-13'),
    ('Math','What is 12! / 11! ?','11','12','13','14','12','12-13'),
    ('Math','A quadrilateral has how many sides?','3','4','5','6','4','12-13'),
    ('Math','What is the area of a circle with radius 7? (π≈22/7)','144','154','164','174','154','12-13'),
    ('Math','What is 2^10?','512','1024','2048','256','1024','12-13'),
    ('Math','The sum of interior angles of a triangle?','90°','180°','270°','360°','180°','12-13'),
    ('Math','Probability of getting heads on a coin flip?','0','1/2','1/4','1/3','1/2','12-13'),
    # ── 12-13 GENERAL KNOWLEDGE ───────────────────────────────────────────────
    ('General Knowledge','Who was the first President of India?','Jawaharlal Nehru','Dr. Rajendra Prasad','Dr. APJ Abdul Kalam','Indira Gandhi','Dr. Rajendra Prasad','12-13'),
    ('General Knowledge','Which is the longest river in the world?','Amazon','Nile','Yangtze','Ganga','Nile','12-13'),
    ('General Knowledge','The United Nations headquarters is in?','Geneva','London','New York','Paris','New York','12-13'),
    ('General Knowledge','Who invented the internet?','Bill Gates','Tim Berners-Lee','Steve Jobs','Mark Zuckerberg','Tim Berners-Lee','12-13'),
    ('General Knowledge','What is the largest democracy in the world?','USA','China','India','Brazil','India','12-13'),
    ('General Knowledge','Which element has the symbol Au?','Silver','Gold','Aluminum','Argon','Gold','12-13'),
    ('General Knowledge','In which year did India gain independence?','1945','1946','1947','1948','1947','12-13'),
    ('General Knowledge','Who wrote "Discovery of India"?','Mahatma Gandhi','Jawaharlal Nehru','Subhas Chandra Bose','B. R. Ambedkar','Jawaharlal Nehru','12-13'),
    # ── 12-13 RIDDLES ─────────────────────────────────────────────────────────
    ('Riddle','I have keys but no locks. I have space but no room. What am I?','Book','Piano','Keyboard','Safe','Keyboard','12-13'),
    ('Riddle','What can travel the world without moving?','Internet','Stamp','Wind','Letter','Stamp','12-13'),
    ('Riddle','The more you share me, the more I grow. What am I?','Money','Knowledge','Food','Time','Knowledge','12-13'),
    # ── 12-13 TECHNOLOGY ─────────────────────────────────────────────────────
    ('Technology','What does CPU stand for?','Central Processing Unit','Computer Power Unit','Control Program Unit','Central Program Utility','Central Processing Unit','12-13'),
    ('Technology','Which language is used to create web pages?','Python','Java','HTML','C++','HTML','12-13'),
    ('Technology','What does GPS stand for?','Global Positioning System','General Processing Software','Geographic Pixel System','Global Pixel Sensor','Global Positioning System','12-13'),
    ('Technology','What does RAM stand for?','Random Access Memory','Read And Modify','Rapid Application Module','Random Array Memory','Random Access Memory','12-13'),
    ('Technology','Which company made the iPhone?','Samsung','Google','Apple','Microsoft','Apple','12-13'),
    ('Technology','What is 1 Gigabyte equal to?','1000 KB','1000 MB','1024 MB','1024 KB','1024 MB','12-13'),
    # ── INTERNET SAFETY (ALL GROUPS) ─────────────────────────────────────────
    ('Internet Safety','You receive a message from an unknown person asking your address. You should?','Reply with address','Block and tell an adult','Reply but give fake info','Ignore forever','Block and tell an adult','6-8'),
    ('Internet Safety','Which password is strongest?','abc123','password1','My@Dog#2024!','iloveschool','My@Dog#2024!','9-11'),
    ('Internet Safety','What is "phishing"?','A type of fishing sport','Tricking someone to give private info','A coding term','Social media feature','Tricking someone to give private info','9-11'),
    ('Internet Safety','HTTPS in a web address means?','The website is slow','The site is secure','The page has ads','The site is government-run','The site is secure','12-13'),
    ('Internet Safety','What is a safe way to create a password?','Use your birth date','Use your name','Mix letters numbers and symbols','Use "password"','Mix letters numbers and symbols','12-13'),
    ('Internet Safety','You feel sad after using an app. The best action is?','Use it more','Delete all apps','Take a break and talk to a trusted adult','Post about it','Take a break and talk to a trusted adult','9-11'),
    ('Internet Safety','Cyberbullying is when someone?','Teaches coding online','Bullies others using technology','Plays games online','Reports a bad website','Bullies others using technology','6-8'),
    # ── INDIA SPECIAL ─────────────────────────────────────────────────────────
    ('India Special','Which is the national animal of India?','Lion','Elephant','Tiger','Leopard','Tiger','6-8'),
    ('India Special','Holi is the festival of?','Lights','Colours','Sweets','Music','Colours','6-8'),
    ('India Special','How many states are in India?','25','26','28','29','28','9-11'),
    ('India Special','The game of Chess was invented in?','China','India','Egypt','Greece','India','9-11'),
    ('India Special','Which Indian state is famous for its backwaters?','Goa','Tamil Nadu','Kerala','Karnataka','Kerala','12-13'),
    ('India Special','Who is known as the Missile Man of India?','Vikram Sarabhai','APJ Abdul Kalam','C.V. Raman','Homi Bhabha','APJ Abdul Kalam','12-13'),
    # ── FUN FACTS ─────────────────────────────────────────────────────────────
    ('Fun Fact','An octopus has how many hearts?','1','2','3','4','3','6-8'),
    ('Fun Fact','Sharks are older than which ancient creatures?','Crocodiles','Dinosaurs','Whales','Elephants','Dinosaurs','9-11'),
    ('Fun Fact','A group of flamingos is called a?','Pack','Flock','Flamboyance','Colony','Flamboyance','9-11'),
    ('Fun Fact','Honey never spoils. How old is the oldest honey found?','100 years','500 years','3000 years','1000 years','3000 years','12-13'),
    ('Fun Fact','Which fruit has seeds on the outside?','Apple','Strawberry','Grape','Orange','Strawberry','6-8'),
    ('Fun Fact','A snail can sleep for how long?','1 day','1 week','3 years','1 month','3 years','9-11'),
    # ── ENVIRONMENT ───────────────────────────────────────────────────────────
    ('Environment','What is the main cause of global warming?','More sunlight','Greenhouse gases','Less rainfall','Earthquakes','Greenhouse gases','9-11'),
    ('Environment','The 3 Rs of environment are?','Read Run Rest','Reduce Reuse Recycle','Race Run Resolve','Run Relay Race','Reduce Reuse Recycle','6-8'),
    ('Environment','Which gas is known as the greenhouse gas?','Oxygen','Nitrogen','Carbon Dioxide','Hydrogen','Carbon Dioxide','12-13'),
    ('Environment','Deforestation mainly causes?','More rain','Soil erosion','Better roads','Cooler weather','Soil erosion','9-11'),
    # ── SPACE ─────────────────────────────────────────────────────────────────
    ('Space','How long does it take Earth to orbit the Sun?','24 hours','365 days','7 days','30 days','365 days','6-8'),
    ('Space','What is the closest star to Earth?','Sirius','Alpha Centauri','The Sun','Vega','The Sun','9-11'),
    ('Space','Who was the first human to walk on the Moon?','Yuri Gagarin','Neil Armstrong','Buzz Aldrin','John Glenn','Neil Armstrong','9-11'),
    ('Space','The Milky Way is a?','Planet','Star','Solar System','Galaxy','Galaxy','12-13'),
    ('Space','What is a black hole?','A hole in space','Region where gravity is so strong nothing escapes','A very dark planet','Space debris','Region where gravity is so strong nothing escapes','12-13'),
    # ── CODING / TECH FOR KIDS ────────────────────────────────────────────────
    ('Coding','In coding, what does "loop" mean?','A bug','Repeating code','A type of variable','A function name','Repeating code','9-11'),
    ('Coding','What is the output of: print(2 + 3) in Python?','23','5','2+3','Error','5','12-13'),
    ('Coding','What does "if" do in programming?','Loops code','Makes a decision','Defines a variable','Prints output','Makes a decision','9-11'),
    ('Coding','The first programming language was called?','Python','Java','FORTRAN','C','FORTRAN','12-13'),
    ('Coding','What is a "bug" in software?','An insect','An error in code','A feature','A slow computer','An error in code','9-11'),
    # ── HEALTH & BODY ─────────────────────────────────────────────────────────
    ('Health','How many teeth do adults have?','28','30','32','34','32','9-11'),
    ('Health','Which vitamin do we get from sunlight?','Vitamin A','Vitamin B','Vitamin C','Vitamin D','Vitamin D','6-8'),
    ('Health','The heart pumps?','Air','Water','Blood','Food','Blood','6-8'),
    ('Health','How many chambers does the human heart have?','2','3','4','5','4','12-13'),
    ('Health','Which mineral makes bones strong?','Iron','Calcium','Potassium','Zinc','Calcium','9-11'),
]

# Additional deterministic local fallback bank. These questions intentionally use
# the existing storage bands (6-8, 9-11, 12-13, 14-18); account creation still
# limits children to ages 6-17, so the final band serves ages 14-17.
EXTRA_QUESTIONS = [
    # ── 6-8 EXTRA ────────────────────────────────────────────────────────────
    ('Math','What is 9 + 6?','13','14','15','16','15','6-8'),
    ('Math','What is 18 - 7?','9','10','11','12','11','6-8'),
    ('Math','What is 5 × 3?','8','10','15','20','15','6-8'),
    ('Math','How many items are in one dozen?','10','11','12','20','12','6-8'),
    ('Math','Which shape has four equal sides?','Triangle','Square','Circle','Oval','Square','6-8'),
    ('Science','What do plant roots mainly absorb from soil?','Water','Sunlight','Smoke','Plastic','Water','6-8'),
    ('Science','What is frozen water called?','Steam','Ice','Rain','Cloud','Ice','6-8'),
    ('Science','Which is the largest land animal?','Tiger','Elephant','Horse','Bear','Elephant','6-8'),
    ('General Knowledge','What day comes after Monday?','Sunday','Tuesday','Friday','Saturday','Tuesday','6-8'),
    ('General Knowledge','What is the first month of the year?','March','January','June','December','January','6-8'),
    ('General Knowledge','100 paise make how many rupees?','1','2','5','10','1','6-8'),
    ('Animals','A baby dog is called a?','Kitten','Puppy','Calf','Cub','Puppy','6-8'),
    ('Health','Which drink is best when you are thirsty?','Water','Ink','Oil','Paint','Water','6-8'),
    ('Environment','Which item can usually be recycled?','Paper','Mud','Smoke','Sunlight','Paper','6-8'),
    ('Environment','What are the 3 Rs?','Run Rest Read','Reduce Reuse Recycle','Red Round Ready','Ride Race Repeat','Reduce Reuse Recycle','6-8'),
    ('Technology','Which device has keys you press to type letters?','Keyboard','Speaker','Monitor','Camera','Keyboard','6-8'),
    ('Internet Safety','Should you share your password with a stranger online?','Yes','Only once','No','Only at night','No','6-8'),
    ('Internet Safety','If an unknown person online asks where you live, what should you do?','Tell them','Send a photo','Tell a trusted adult','Give a fake address','Tell a trusted adult','6-8'),
    ('Road Safety','Where should you cross a busy road when available?','Anywhere','At a pedestrian crossing','Between parked cars','While running','At a pedestrian crossing','6-8'),
    ('Science','Earth is shaped most like a?','Cube','Ball','Triangle','Flat sheet','Ball','6-8'),

    # ── 9-11 EXTRA ───────────────────────────────────────────────────────────
    ('Math','What is half of 50?','20','25','30','35','25','9-11'),
    ('Math','What is the area of a rectangle 8 cm by 5 cm?','13 cm²','26 cm²','40 cm²','80 cm²','40 cm²','9-11'),
    ('Math','Which number is prime?','15','17','21','27','17','9-11'),
    ('Math','What is 0.5 as a fraction?','1/4','1/2','2/3','3/4','1/2','9-11'),
    ('Math','A right angle measures?','45°','60°','90°','180°','90°','9-11'),
    ('Math','What is the HCF of 12 and 18?','2','3','6','9','6','9-11'),
    ('Math','What is the perimeter of a 6 cm by 4 cm rectangle?','10 cm','20 cm','24 cm','40 cm','20 cm','9-11'),
    ('Science','Which organ pumps blood around the body?','Lungs','Heart','Stomach','Kidneys','Heart','9-11'),
    ('Science','Earth spinning on its axis causes?','Seasons only','Day and night','Tides only','Rainbows','Day and night','9-11'),
    ('Science','Liquid water changing into water vapour is called?','Freezing','Evaporation','Melting','Condensation','Evaporation','9-11'),
    ('Science','Plants release which gas during photosynthesis?','Oxygen','Helium','Hydrogen','Methane','Oxygen','9-11'),
    ('Science','Which is the largest mammal?','Elephant','Blue whale','Giraffe','Hippopotamus','Blue whale','9-11'),
    ('Science','The centre of our solar system is the?','Earth','Moon','Sun','Mars','Sun','9-11'),
    ('Environment','Which is a renewable energy source?','Coal','Petrol','Solar energy','Diesel','Solar energy','9-11'),
    ('Environment','In a simple food chain, green plants are usually?','Producers','Predators','Scavengers','Decomposers only','Producers','9-11'),
    ('Technology','Binary numbers use which two digits?','0 and 1','1 and 2','2 and 3','8 and 9','0 and 1','9-11'),
    ('Technology','What is the main job of a web browser?','Wash files','Open and view websites','Charge a battery','Print money','Open and view websites','9-11'),
    ('Internet Safety','What does two-factor authentication add?','A second security check','More advertisements','A larger screen','Faster typing','A second security check','9-11'),
    ('Internet Safety','An unexpected message asks you to click a link and enter your password. What should you do?','Click quickly','Forward your password','Avoid the link and verify the sender','Reply with your address','Avoid the link and verify the sender','9-11'),
    ('General Knowledge','India is part of which continent?','Europe','Asia','Africa','South America','Asia','9-11'),

    # ── 12-13 EXTRA ──────────────────────────────────────────────────────────
    ('Math','Solve: 4x = 28. What is x?','5','6','7','8','7','12-13'),
    ('Math','What is the mean of 4, 6 and 8?','5','6','7','8','6','12-13'),
    ('Math','A fair die is rolled. Probability of an even number is?','1/6','1/3','1/2','2/3','1/2','12-13'),
    ('Math','A right triangle has sides 3 and 4. Its hypotenuse is?','5','6','7','8','5','12-13'),
    ('Math','A car travels 150 km in 3 hours. Average speed is?','30 km/h','40 km/h','50 km/h','60 km/h','50 km/h','12-13'),
    ('Science','What is the SI unit of force?','Joule','Newton','Pascal','Watt','Newton','12-13'),
    ('Science','What is the chemical symbol for sodium?','So','Sd','Na','Sn','Na','12-13'),
    ('Science','A substance with pH below 7 is generally?','Acidic','Neutral','Basic','Radioactive','Acidic','12-13'),
    ('Science','DNA in a typical human cell is mainly stored in the?','Cell wall','Nucleus','Vacuole','Cytoplasm only','Nucleus','12-13'),
    ('Science','Mitosis normally produces how many daughter cells?','1','2','3','4','2','12-13'),
    ('Science','Which is a common greenhouse gas?','Carbon dioxide','Helium','Neon','Argon only','Carbon dioxide','12-13'),
    ('Health','What is the largest organ of the human body?','Heart','Liver','Skin','Lung','Skin','12-13'),
    ('Technology','HTML stands for?','HyperText Markup Language','High Transfer Machine Language','Home Tool Markup Link','Hyper Terminal Main Logic','HyperText Markup Language','12-13'),
    ('Technology','RAM is mainly used for?','Temporary working memory','Permanent paper storage','Internet cables','Cooling the computer','Temporary working memory','12-13'),
    ('Technology','Binary 1010 equals which decimal number?','8','9','10','12','10','12-13'),
    ('Technology','An algorithm is best described as?','A random picture','A step-by-step procedure','A hardware cable','A password only','A step-by-step procedure','12-13'),
    ('Internet Safety','HTTPS mainly indicates that the connection to a website is?','Encrypted','Always free','Offline','A video game','Encrypted','12-13'),
    ('Internet Safety','Which is safest for an important account?','Reuse one password everywhere','Use a strong unique password','Share the password with friends','Write it in a public post','Use a strong unique password','12-13'),
    ('Environment','Which energy source uses moving air?','Wind energy','Coal energy','Diesel energy','Natural gas','Wind energy','12-13'),
    ('Logic','If all squares are rectangles, which statement is true?','Every rectangle is a square','Every square is a rectangle','No square is a rectangle','Squares have three sides','Every square is a rectangle','12-13'),

    # ── 14-18 LOCAL FALLBACK ─────────────────────────────────────────────────
    ('Math','Solve: x² = 49. What are the real values of x?','7 only','-7 only','7 and -7','49 and 1','7 and -7','14-18'),
    ('Math','What is the slope of the line through (0,0) and (2,6)?','2','3','4','6','3','14-18'),
    ('Math','Simple interest on ₹1000 at 10% per year for 2 years is?','₹100','₹150','₹200','₹300','₹200','14-18'),
    ('Math','Two fair coins are tossed. Probability of two heads is?','1/2','1/3','1/4','3/4','1/4','14-18'),
    ('Math','The roots of x² - 5x + 6 = 0 are?','1 and 6','2 and 3','-2 and -3','3 and 6','2 and 3','14-18'),
    ('Math','What is log₁₀(1000)?','1','2','3','10','3','14-18'),
    ('Math','The derivative of x² with respect to x is?','x','2x','x²','2','2x','14-18'),
    ('Math','What is the median of 2, 4, 7, 9, 12?','4','7','8','9','7','14-18'),
    ('Science','The SI unit of acceleration is?','m/s','m/s²','kg/m','N/s','m/s²','14-18'),
    ('Science','Ohm’s law is commonly written as?','V = IR','P = VI','F = ma','E = mc²','V = IR','14-18'),
    ('Science','Kinetic energy is given by?','mv','mgh','½mv²','F/a','½mv²','14-18'),
    ('Science','Which organelle produces most cellular ATP?','Ribosome','Mitochondrion','Golgi body','Lysosome','Mitochondrion','14-18'),
    ('Science','In DNA, adenine normally pairs with?','Cytosine','Guanine','Thymine','Uracil','Thymine','14-18'),
    ('Science','In DNA, cytosine normally pairs with?','Adenine','Guanine','Thymine','Uracil','Guanine','14-18'),
    ('Science','Oxidation can be described as?','Gain of electrons','Loss of electrons','No electron change','Only cooling','Loss of electrons','14-18'),
    ('Science','Wave speed is related to frequency and wavelength by?','v = fλ','v = f/λ','v = λ/f','v = f + λ','v = fλ','14-18'),
    ('Science','Which gas is a major contributor to human-caused greenhouse warming?','Carbon dioxide','Helium','Neon','Argon','Carbon dioxide','14-18'),
    ('Science','Earthquakes are strongly associated with movement of?','Cloud layers','Tectonic plates','Ocean salt','Moonlight','Tectonic plates','14-18'),
    ('Technology','DNS mainly converts a domain name into?','An IP address','A password','A file extension','A keyboard shortcut','An IP address','14-18'),
    ('Technology','SQL SELECT is mainly used to?','Read data','Delete an operating system','Encrypt a hard drive','Compile Java','Read data','14-18'),
    ('Technology','Git is primarily a?','Spreadsheet','Version control system','Web browser','Database engine','Version control system','14-18'),
    ('Technology','An API allows software systems to?','Communicate through defined interfaces','Share every password','Avoid all networks','Replace electricity','Communicate through defined interfaces','14-18'),
    ('Technology','A cryptographic hash is designed to be?','A one-way digest','A reversible plain-text copy','A video format','A network cable','A one-way digest','14-18'),
    ('Technology','Which Boolean expression is true only when both A and B are true?','A OR B','A AND B','NOT A','A XOR B','A AND B','14-18'),
    ('Technology','Binary 1111 equals decimal?','12','13','14','15','15','14-18'),
    ('Technology','Hexadecimal F equals decimal?','14','15','16','255','15','14-18'),
    ('Technology','An O(n) algorithm is commonly described as?','Constant time','Linear time','Quadratic time','Exponential time','Linear time','14-18'),
    ('Technology','An IP address is used to?','Identify a network interface/location on an IP network','Measure battery charge','Store a photo caption','Create a keyboard font','Identify a network interface/location on an IP network','14-18'),
    ('Internet Safety','An OTP sent for login should be shared with?','Anyone who asks','Only close friends','Nobody else','A public group','Nobody else','14-18'),
    ('Internet Safety','A strong defence against account takeover is?','Reuse passwords','Unique passwords plus MFA','Disable screen lock','Post recovery codes publicly','Unique passwords plus MFA','14-18'),
    ('Internet Safety','Before trusting a surprising online claim, you should?','Share immediately','Check reliable independent sources','Assume every screenshot is true','Ignore the source','Check reliable independent sources','14-18'),
    ('Internet Safety','On public Wi-Fi, the safest choice for a sensitive login is to?','Use a trusted secure connection if possible','Turn off the screen only','Share the password first','Disable HTTPS','Use a trusted secure connection if possible','14-18'),
    ('Internet Safety','Phishing usually tries to make a user?','Reveal sensitive information','Improve battery life','Compress photos','Learn mathematics','Reveal sensitive information','14-18'),
    ('Environment','Biodiversity means the?','Variety of living organisms','Amount of rainfall only','Number of roads','Speed of wind','Variety of living organisms','14-18'),
    ('Environment','Which is a renewable source of electricity?','Solar','Coal','Diesel','Petrol','Solar','14-18'),
    ('Environment','A carbon footprint is related to?','Greenhouse gas emissions','Shoe size','Internet speed','Ocean depth','Greenhouse gas emissions','14-18'),
    ('Health','Which nutrient is the body’s main immediate energy source?','Carbohydrates','Water only','Minerals only','Vitamins only','Carbohydrates','14-18'),
    ('Health','Which organ primarily filters blood to produce urine?','Kidneys','Lungs','Stomach','Pancreas','Kidneys','14-18'),
    ('Logic','If P is true and Q is false, P AND Q is?','True','False','Undefined','Both','False','14-18'),
    ('Logic','If a statement is true, its logical NOT is?','True','False','Always unknown','A number','False','14-18'),
]

QUESTIONS.extend(EXTRA_QUESTIONS)

INSERT_SQL = """
INSERT INTO quizzes(category, question, option_a, option_b, option_c, option_d, correct_answer, age_group)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""

def run():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, QUESTIONS)
            count = cur.rowcount
        conn.commit()
        print(f'[OK] Seeded {count} new quiz questions ({len(QUESTIONS)} total attempted).')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    run()
