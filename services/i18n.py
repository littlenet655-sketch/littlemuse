from database.connection import fetch_one, execute

LANGUAGES={'EN':'English','KN':'ಕನ್ನಡ','HI':'हिन्दी'}
TEXT={
 'EN':{
  'home':'Home','discover':'Discover','create':'Create','reels':'Reels','profile':'Profile','notifications':'Notifications','messages':'Messages',
  'overview':'Overview','safety_review':'Safety Review','connections':'Connections','screen_time':'Screen Time','learning':'Learning','alerts':'Alerts','activity':'Activity',
  'controls':'Controls','switch_mode':'Switch mode','language':'Language','save':'Save','kids_safe':'Kids Safe','for_you':'For You','see_all':'See all',
  'parent_mode':'Parent Mode','educational_feed':'Educational-only feed','allowed_categories':'Allowed content categories','posting':'Posting','stories':'Stories','messaging':'Messaging','discover_feature':'Discover','reels_feature':'Reels',
  'parent_controls':'Smart Parent Controls','age_group':'Audience age group','all_ages':'All ages','restricted_parent':'This feature is disabled by Parent Mode.',
  'tagline':'A safer place to connect, create and learn.','kids_mode':'Kids Mode','safe_social_desc':'Safe social feed, Reels, stories, learning and approved chats.','parent_mode_desc':'Review safety, connections, screen time and learning.','create_parent':'Create Parent Mode account','child_first':'Child-first approval flow','email':'Email','password':'Password','login':'Log in','search_students':'Search students','following':'Following','requested':'Requested','follow':'Follow','posts':'posts','followers':'followers','change_photo':'Change photo','live_safety':'Live Safety','saved':'Saved','children':'Children','create_child':'+ Create child','today':'Today','unread_alert':'unread alert','quiz_settings':'Quiz settings','learning_report':'Learning report','interests':'Interests','usage':'Usage','behaviour':'Behaviour','save_safety':'Save safety','no_children':'No child is linked to this Parent Mode account.','safety_intro':'18+ and weapon content never appears here. Those categories are hard-blocked automatically. This queue is only for uncertain or medium-risk content.','risk':'Risk','adult':'Adult','violence':'Violence','weapon':'Weapon','toxicity':'Toxicity','inspect':'Inspect content before deciding','approve':'Approve','block':'Block','no_review':'No content is waiting for review.','server_enforced':'These controls are enforced on the server, not only hidden in the app UI.','challenges':'Challenges','points':'pts','completed':'Completed','your_answer':'Your answer','write_response':'Write your response','complete_challenge':'Complete challenge','no_challenges':'No challenges are available for this age group yet.','educational_reel':'Educational Reel','safe_feed_ready':'Your safe feed is ready','safe_feed_hint':'Follow approved classmates or update Parent Mode content controls.','create_post':'Create','post_type':'Post type','post':'Post','story':'Story','media':'Photo, video or audio','story_music':'Optional Story music/audio','caption':'Caption / text post','category':'Category','publish':'Check safety & publish','moderation_note':'All content is moderated before Kids Mode can display it. 18+ content is hard-blocked.','based_interests':'Based on parent-approved interests','recommendation_hint':'Once Parent Mode approves interests and connections, recommendations will appear here.','approved_connection':'Parent-approved connection'
 },
 'KN':{
  'home':'ಮುಖಪುಟ','discover':'ಹುಡುಕಿ','create':'ರಚಿಸಿ','reels':'ರೀಲ್ಸ್','profile':'ಪ್ರೊಫೈಲ್','notifications':'ಸೂಚನೆಗಳು','messages':'ಸಂದೇಶಗಳು',
  'overview':'ಒಟ್ಟಾರೆ','safety_review':'ಸುರಕ್ಷತಾ ಪರಿಶೀಲನೆ','connections':'ಸಂಪರ್ಕಗಳು','screen_time':'ಸ್ಕ್ರೀನ್ ಸಮಯ','learning':'ಕಲಿಕೆ','alerts':'ಎಚ್ಚರಿಕೆಗಳು','activity':'ಚಟುವಟಿಕೆ',
  'controls':'ನಿಯಂತ್ರಣಗಳು','switch_mode':'ಮೋಡ್ ಬದಲಿಸಿ','language':'ಭಾಷೆ','save':'ಉಳಿಸಿ','kids_safe':'ಮಕ್ಕಳಿಗೆ ಸುರಕ್ಷಿತ','for_you':'ನಿಮಗಾಗಿ','see_all':'ಎಲ್ಲ ನೋಡಿ',
  'parent_mode':'ಪೋಷಕರ ಮೋಡ್','educational_feed':'ಶೈಕ್ಷಣಿಕ ವಿಷಯ ಮಾತ್ರ','allowed_categories':'ಅನುಮತಿಸಿದ ವಿಷಯ ವಿಭಾಗಗಳು','posting':'ಪೋಸ್ಟ್ ಮಾಡುವುದು','stories':'ಸ್ಟೋರೀಸ್','messaging':'ಸಂದೇಶಗಳು','discover_feature':'ಡಿಸ್ಕವರ್','reels_feature':'ರೀಲ್ಸ್',
  'parent_controls':'ಸ್ಮಾರ್ಟ್ ಪೋಷಕರ ನಿಯಂತ್ರಣಗಳು','age_group':'ಪ್ರೇಕ್ಷಕರ ವಯೋಮಿತಿ','all_ages':'ಎಲ್ಲಾ ವಯಸ್ಸು','restricted_parent':'ಈ ವೈಶಿಷ್ಟ್ಯವನ್ನು ಪೋಷಕರ ಮೋಡ್ ನಿಷ್ಕ್ರಿಯಗೊಳಿಸಿದೆ.'
 },
 'HI':{
  'home':'होम','discover':'खोजें','create':'बनाएँ','reels':'रील्स','profile':'प्रोफ़ाइल','notifications':'सूचनाएँ','messages':'संदेश',
  'overview':'ओवरव्यू','safety_review':'सुरक्षा समीक्षा','connections':'कनेक्शन','screen_time':'स्क्रीन टाइम','learning':'लर्निंग','alerts':'अलर्ट','activity':'गतिविधि',
  'controls':'कंट्रोल','switch_mode':'मोड बदलें','language':'भाषा','save':'सेव करें','kids_safe':'बच्चों के लिए सुरक्षित','for_you':'आपके लिए','see_all':'सभी देखें',
  'parent_mode':'पैरेंट मोड','educational_feed':'केवल शैक्षणिक फ़ीड','allowed_categories':'अनुमत कंटेंट श्रेणियाँ','posting':'पोस्टिंग','stories':'स्टोरीज़','messaging':'मैसेजिंग','discover_feature':'डिस्कवर','reels_feature':'रील्स',
  'parent_controls':'स्मार्ट पैरेंट कंट्रोल','age_group':'दर्शक आयु समूह','all_ages':'सभी आयु','restricted_parent':'यह सुविधा पैरेंट मोड द्वारा बंद की गई है।'
 }
}

def language_for_user(user_id):
    if not user_id:return 'EN'
    row=fetch_one('SELECT preferred_language FROM user_preferences WHERE user_id=%s',(user_id,))
    lang=(row or {}).get('preferred_language','EN') if row else 'EN'
    return lang if lang in LANGUAGES else 'EN'

def set_language(user_id,lang):
    lang=lang if lang in LANGUAGES else 'EN'
    execute('''INSERT INTO user_preferences(user_id,preferred_language,updated_at) VALUES(%s,%s,NOW())
      ON CONFLICT(user_id) DO UPDATE SET preferred_language=EXCLUDED.preferred_language,updated_at=NOW()''',(user_id,lang))
    return lang

def tr(lang,key):
    return TEXT.get(lang,TEXT['EN']).get(key,TEXT['EN'].get(key,key))
