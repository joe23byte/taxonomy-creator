"""Generate the reproducible synthetic telco dataset (100 conversations).

Outputs (backend/data/sample/):
- sample_transcripts.json   canonical import format (no labels)
- sample_transcripts.csv    same data, one row per conversation with a transcript column
- sample_ground_truth.json  intent labels per conversation (kept separate; never used by the pipeline)
- import_template.csv       minimal CSV template for user data

Run:  python scripts/generate_sample_data.py
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261020
N_CONVERSATIONS = 100
OUT = Path(__file__).resolve().parent.parent / "data" / "sample"

# key: (label, l1, l2, occurrences, segment constraint)
INTENTS = {
    "duplicate_charge": ("Duplicate charge", "L1-BIL", "L2-BIL-DSP", 11, "postpaid"),
    "missing_topup": ("Missing prepaid top-up", "L1-PRD", "L2-PRD-TOP", 10, "prepaid"),
    "slow_data": ("Slow mobile data", "L1-NET", "L2-NET-DAT", 10, None),
    "invoice_explanation": ("Invoice explanation", "L1-BIL", "L2-BIL-INV", 9, "postpaid"),
    "roaming_charges": ("Incorrect roaming fees", "L1-BIL", "L2-BIL-DSP", 7, "postpaid"),
    "password_reset": ("Password reset", "L1-ACC", "L2-ACC-ACS", 7, None),
    "failed_payment": ("Failed payment", "L1-BIL", "L2-BIL-PAY", 7, "postpaid"),
    "network_outage": ("Network outage", "L1-NET", "L2-NET-COV", 6, None),
    "tariff_upgrade": ("Tariff upgrade", "L1-PRD", "L2-PRD-TAR", 6, None),
    "bundle_activation": ("Bundle activation", "L1-PRD", "L2-PRD-BUN", 6, None),
    "call_quality": ("Call quality problems", "L1-NET", "L2-NET-VOC", 5, None),
    "sim_activation": ("SIM activation", "L1-ACC", "L2-ACC-SIM", 4, None),
    "incorrect_data_usage": ("Incorrect data usage", "L1-PRD", "L2-PRD-BUN", 4, None),
    "account_locked": ("Account locked", "L1-ACC", "L2-ACC-ACS", 4, None),
    "contract_cancellation": ("Contract cancellation", "L1-PRD", "L2-PRD-CON", 4, "postpaid"),
    "subscription_renewal": ("Unexpected subscription renewal", "L1-PRD", "L2-PRD-CON", 3, None),
    "tariff_downgrade": ("Tariff downgrade", "L1-PRD", "L2-PRD-TAR", 3, None),
    "overage_charges": ("Incorrect data overage charges", "L1-BIL", "L2-BIL-DSP", 2, "postpaid"),
    "lost_sim": ("Lost SIM replacement", "L1-ACC", "L2-ACC-SIM", 2, None),
    "sim_swap": ("SIM swap request", "L1-ACC", "L2-ACC-SIM", 2, None),
    "number_porting": ("Number porting", "L1-PRD", "L2-PRD-POR", 1, None),
    "address_change": ("Address change", "L1-ACC", "L2-ACC-DET", 1, None),
}

# Customer wording variants. "opener" starts a conversation, "also" adds a secondary intent,
# "vague" is used for deliberately ambiguous conversations.
T: dict[str, dict[str, list[str]]] = {
    "duplicate_charge": {
        "opener": [
            "Hi, I just looked at my bill and I've been charged twice for the same month.",
            "My bank statement shows two debits of {amount} from you this month. Why did you take the money twice?",
            "Hello, there's a double charge on my invoice — the monthly fee appears two times.",
            "I paid my bill and then you took the payment again a few days later. I want the duplicate back.",
            "You billed me {amount} twice for my contract this month, that can't be right.",
        ],
        "detail": [
            "Both charges are for {amount}, on the {date1} and the {date2}.",
            "It's the exact same amount, {amount}, listed twice under monthly charges.",
            "I can see two identical transactions on my banking app, both from you.",
        ],
        "agent_q": ["I'm sorry about that. Can you tell me the amount and the dates of both charges?",
                    "Let me look into that. Which billing period are we talking about?"],
        "resolve": ["I can confirm the duplicate charge. I've raised a refund of {amount}, it will be back on your account within five working days.",
                    "You're right, the monthly fee was applied twice due to a system error. The second charge has been reversed."],
        "also": ["Also, I think I was charged twice for last month as well, can you check that too?",
                 "And one more thing — there's a duplicate payment on my account from {date1}."],
        "vague": ["Hi, something on my bill doesn't add up, it feels like I'm paying more than I should."],
    },
    "missing_topup": {
        "opener": [
            "I topped up my prepaid account yesterday, but the credit is still missing.",
            "Hi, I bought a {amount} voucher this morning and my balance hasn't changed.",
            "I recharged my number online and the money left my card, but I don't see the credit on my phone.",
            "My top-up didn't arrive. I paid {amount} at the shop and nothing happened.",
            "Hello, I loaded credit through the app two hours ago and my balance still shows zero.",
        ],
        "detail": ["I did it through the app at around {time}, I have the confirmation email.",
                   "The receipt from the shop says the transaction was successful.",
                   "The payment shows as completed on my card, {amount}."],
        "agent_q": ["Sorry to hear that. Can you tell me how and when you made the top-up?",
                    "Do you have a transaction reference or receipt for the top-up?"],
        "resolve": ["I found the transaction, it was stuck in processing. I've applied the {amount} credit manually, you should see it now.",
                    "The top-up failed on our side. I've credited {amount} to your balance, please restart your phone."],
        "also": ["Oh, and the top-up I made last week never showed up either.",
                 "Also my credit from the {amount} recharge is missing, can you look at that as well?"],
        "vague": ["My balance looks weird since yesterday, I'm not sure what happened to my money."],
    },
    "slow_data": {
        "opener": [
            "My mobile internet has been extremely slow for the last few days.",
            "Hi, the data on my phone is crawling, I can barely load a web page.",
            "Videos keep buffering and apps take forever to load on mobile data. It used to be fast.",
            "My 4G is basically unusable, speeds are terrible since last week.",
            "Internet on my phone is so slow I can't even send pictures on WhatsApp.",
        ],
        "detail": ["It's slow everywhere, at home in {city} and at work.",
                   "I ran a speed test and got less than 1 Mbit per second.",
                   "Wi-Fi is fine, it's only the mobile data that is slow."],
        "agent_q": ["I'm sorry about that. Where do you notice the slow speeds, and since when?",
                    "Have you already tried restarting your phone or toggling airplane mode?"],
        "resolve": ["I've refreshed your network settings and there was a capacity issue on a mast near you that has been fixed.",
                    "Your device was stuck on an old network profile. I've pushed new settings, please restart the phone."],
        "also": ["Also, my mobile internet has been really slow lately, is something wrong?",
                 "One more thing, the data speed on my phone is awful in the evenings."],
        "vague": ["My phone is just not working properly, the internet thing is weird and slow sometimes, I don't really know."],
    },
    "invoice_explanation": {
        "opener": [
            "Hi, can you explain my latest invoice? I don't understand some of the line items.",
            "My bill is higher than usual this month and I don't know why.",
            "What is this 'service adjustment' charge on my invoice?",
            "I received my first bill and it's confusing, why is it {amount} instead of my monthly price?",
            "Could someone go through my bill with me? There are several items I don't recognise.",
        ],
        "detail": ["Normally I pay around {amount} but this month it's quite a bit more.",
                   "There's a line called 'pro-rata charges' that I've never seen before.",
                   "I just want to understand what each part of the bill is for."],
        "agent_q": ["Of course, I'd be happy to go through it. Which items are unclear?",
                    "Sure, let me open your latest invoice. What exactly looks unusual?"],
        "resolve": ["The extra amount is a pro-rata charge because your plan changed mid-cycle. Next month it will be back to normal.",
                    "That line is the partial month from when your contract started. Everything on the bill is correct."],
        "also": ["And while I have you, can you explain what the extra charges on my invoice are?",
                 "Also, my bill has a line item I don't understand, can you explain it?"],
        "vague": ["My bill this month just seems strange to me, I'm not sure if something is wrong or if I'm misreading it."],
    },
    "roaming_charges": {
        "opener": [
            "I was in {country} last week and got charged roaming fees even though roaming should be included in my plan.",
            "My bill has {amount} of roaming charges from my holiday, that's way too much.",
            "Hi, why am I being billed for roaming? I only used my phone on Wi-Fi when I was abroad.",
            "I got a huge roaming charge from my trip to {country}, I think it's a mistake.",
        ],
        "detail": ["I had the travel pass activated before I left.",
                   "I was only there for three days and barely used data.",
                   "The charge is listed as international data usage in {country}."],
        "agent_q": ["I understand. Which country were you in and on what dates?",
                    "Let me check your roaming usage. Did you have a travel add-on active?"],
        "resolve": ["The travel pass was not applied correctly. I've removed the {amount} roaming charges from your bill.",
                    "I can see the charges came from a network outside the included zone. As a goodwill gesture I've credited half."],
        "also": ["Also, there are roaming fees on my bill from my trip to {country} that shouldn't be there.",
                 "One more thing, I was charged for roaming in {country} even though it's in the EU."],
        "vague": [],
    },
    "password_reset": {
        "opener": [
            "I forgot my password for the online account, how can I reset it?",
            "Hi, I can't remember my login password for the app.",
            "The password reset email never arrives, can you help me get into my account?",
            "I need to reset my password, the 'forgot password' link isn't working for me.",
        ],
        "detail": ["I tried the reset link three times but nothing comes through.",
                   "I changed my email recently, maybe that's the problem.",
                   "I just need to log in to download my bill."],
        "agent_q": ["No problem. Can you confirm the email address registered on your account?",
                    "I can help with that. Which email address do you use to log in?"],
        "resolve": ["I've sent a new password reset link to your email, it's valid for 30 minutes.",
                    "Your account email was outdated. I've updated it and triggered a new reset link."],
        "also": ["Also, I forgot the password for my online account, can you send me a reset link?",
                 "And I need to reset my app password, I can't remember it."],
        "vague": [],
    },
    "failed_payment": {
        "opener": [
            "My payment for this month's bill keeps failing.",
            "Hi, I tried to pay my invoice online but the payment was declined.",
            "I got a message that my direct debit failed, but there's enough money in my account.",
            "Every time I try to pay with my card on your website, it says payment unsuccessful.",
        ],
        "detail": ["I tried two different cards, both declined.",
                   "The bank says they didn't block anything on their side.",
                   "I got an error code at the last step of the checkout."],
        "agent_q": ["I'm sorry about that. How are you trying to pay — card, direct debit or bank transfer?",
                    "Can you tell me what error message you see when the payment fails?"],
        "resolve": ["There was an issue with the payment provider earlier today. I've taken the payment manually over the phone, it went through.",
                    "Your direct debit mandate had expired. I've set up a new one, and no late fee will be charged."],
        "also": ["Also, my last payment didn't go through, I don't know why.",
                 "And my card payment for the bill was declined yesterday, can you check?"],
        "vague": [],
    },
    "network_outage": {
        "opener": [
            "There's no signal at all in {city} since this morning. Is there an outage?",
            "Hi, my phone has shown 'no service' for hours, and my neighbours have the same problem.",
            "Is the network down? I can't make calls or use data anywhere in my area.",
            "Your network has been completely dead in my neighbourhood since last night.",
        ],
        "detail": ["It's the whole area around {city} centre, everyone on your network is affected.",
                   "My phone just says 'emergency calls only'.",
                   "It started around {time} yesterday."],
        "agent_q": ["I'm sorry. Can you give me your postcode so I can check for outages?",
                    "Let me check the network status in your area. Which town are you in?"],
        "resolve": ["Yes, there's a confirmed outage in {city} due to a damaged fibre link. Engineers expect it to be fixed by this evening.",
                    "There is planned maintenance on a mast near you. Service should be restored within a few hours."],
        "also": ["Also, is there a network outage in {city}? I had no signal at all yesterday.",
                 "And by the way, the whole network was down in my area this morning."],
        "vague": [],
    },
    "tariff_upgrade": {
        "opener": [
            "I'd like to upgrade to a plan with more data.",
            "Hi, my current tariff isn't enough anymore, what bigger plans do you have?",
            "Can I switch to the unlimited plan? I keep running out of data.",
            "I want to move to a better tariff with 5G and more gigabytes.",
        ],
        "detail": ["I use around 30 GB a month now because of streaming.",
                   "I'd like something with unlimited data if the price is reasonable.",
                   "My current plan only has 10 GB."],
        "agent_q": ["Sure! How much data do you typically use per month?",
                    "Happy to help. Are you looking for unlimited data or a specific amount?"],
        "resolve": ["I've upgraded you to the Unlimited Plus plan at {amount} per month, starting today.",
                    "You're now on the 50 GB plan. The new price applies from your next billing cycle."],
        "also": ["Also, I'd like to upgrade my plan to one with more data.",
                 "And can you tell me about bigger tariffs? I want more data."],
        "vague": [],
    },
    "bundle_activation": {
        "opener": [
            "I bought the 10 GB data add-on but it hasn't been activated.",
            "Hi, how do I activate the international calls bundle?",
            "I purchased the weekend data pack in the app but I can't use it.",
            "Can you add the streaming bundle to my account? The app keeps showing an error.",
        ],
        "detail": ["I paid for it this morning and still have no extra data.",
                   "The app says 'activation pending' for over a day now.",
                   "I want it to start today if possible."],
        "agent_q": ["Let me check. Which bundle did you purchase and when?",
                    "Of course. Which add-on would you like to activate?"],
        "resolve": ["The bundle was stuck in activation. I've activated it manually, you should have the extra data now.",
                    "I've added the bundle to your account; it's active immediately and renews monthly."],
        "also": ["Also, my data add-on that I bought isn't active yet.",
                 "And could you activate the international minutes bundle for me?"],
        "vague": [],
    },
    "call_quality": {
        "opener": [
            "My calls keep dropping after a few seconds.",
            "Hi, the call quality is terrible, people say my voice is breaking up.",
            "I can hear the other person but they can't hear me properly, the sound cuts out constantly.",
            "Calls on my phone are crackly and often disconnect.",
        ],
        "detail": ["It happens mostly at home, but sometimes in the city too.",
                   "It started after the last software update on my phone.",
                   "Calls drop about every two minutes."],
        "agent_q": ["I'm sorry to hear that. Does it happen everywhere or only in certain places?",
                    "Have you noticed this with all contacts or only some?"],
        "resolve": ["I've enabled Voice over LTE on your line, which should improve call quality significantly.",
                    "There's a known issue with a mast near your home that's being repaired. I've logged your case."],
        "also": ["Also, my calls keep cutting out, it's really annoying.",
                 "And the voice quality on calls has been bad lately."],
        "vague": ["My phone is acting up, sometimes I can't hear anything properly, I don't know if it's the phone or you."],
    },
    "sim_activation": {
        "opener": [
            "I received my new SIM card but I can't activate it.",
            "Hi, how do I activate the SIM that came in the post?",
            "My new SIM says 'not registered on network', it hasn't been activated.",
            "I got my SIM yesterday and it still has no service, can you activate it?",
        ],
        "detail": ["I inserted it and restarted the phone several times.",
                   "The activation website gives me an error.",
                   "It's for a new contract I signed last week."],
        "agent_q": ["Sure. Can you read me the last four digits of the SIM card number?",
                    "Let me help. Is this a brand new contract or a replacement SIM?"],
        "resolve": ["I've activated the SIM card now. Please restart your phone, it should connect within ten minutes.",
                    "The activation was pending identity verification. That's complete now and your SIM is active."],
        "also": ["Also, my new SIM card still isn't activated.", "And can you activate my new SIM card as well?"],
        "vague": [],
    },
    "incorrect_data_usage": {
        "opener": [
            "The app says I've used all my data, but I've hardly been online this month.",
            "My data counter is wrong, it shows 15 GB used but I'm always on Wi-Fi.",
            "Hi, my data allowance ran out after a week, that's impossible with how little I use.",
            "I think my data usage is being counted incorrectly.",
        ],
        "detail": ["I'm on Wi-Fi at home and at work almost all the time.",
                   "Last month I used 2 GB, this month it says 15 GB.",
                   "I didn't stream or download anything big."],
        "agent_q": ["Let me check your usage records. When did you notice the change?",
                    "I'll look at the data sessions. Did you install any new apps recently?"],
        "resolve": ["I can see a background app synchronising large files. I've given you a 5 GB courtesy bundle and explained how to restrict it.",
                    "There was a metering error on our side; I've reset your data counter."],
        "also": ["Also, my data usage seems way too high, I don't think it's right.",
                 "And the data counter in the app looks wrong to me."],
        "vague": [],
    },
    "account_locked": {
        "opener": [
            "My online account is locked after too many login attempts.",
            "Hi, the app says my account has been blocked for security reasons.",
            "I can't get into my account, it says it's locked and to contact support.",
        ],
        "detail": ["I entered the wrong PIN a few times and now it's locked.",
                   "I know my password, it's just locked now.",
                   "It's been locked since yesterday."],
        "agent_q": ["For security I need to verify you. Can you confirm your date of birth?",
                    "I can help unlock it. Can you confirm the account holder's name?"],
        "resolve": ["Thanks, I've unlocked your account. You can log in again now.",
                    "The lock has been removed. I recommend enabling two-factor authentication."],
        "also": ["Also, my online account is locked and I can't log in.",
                 "And my account got blocked after I tried logging in a few times."],
        "vague": [],
    },
    "contract_cancellation": {
        "opener": [
            "I want to cancel my contract.",
            "Hi, I'm moving abroad and need to terminate my mobile contract.",
            "How do I cancel my subscription? I'm not happy with the service.",
            "I'd like to end my contract at the end of the minimum term.",
        ],
        "detail": ["My contract ends next month anyway.",
                   "I've found a cheaper offer elsewhere.",
                   "I'm moving to {country} in two months."],
        "agent_q": ["I'm sorry to hear that. May I ask why you want to cancel?",
                    "Let me check your contract end date."],
        "resolve": ["Your cancellation is registered for the end of your minimum term. You'll receive a confirmation letter.",
                    "I've processed the termination; your service ends on the last day of next month."],
        "also": ["And I also want to cancel my contract after that.",
                 "Also, I'm thinking about ending my contract, how do I do that?"],
        "vague": [],
    },
    "subscription_renewal": {
        "opener": [
            "My streaming subscription renewed automatically without asking me.",
            "Hi, I was charged for another year of the music add-on, I never agreed to renew it.",
            "Why did my magazine subscription through you renew? I thought it was a one-month trial.",
        ],
        "detail": ["I never received a reminder before it renewed.",
                   "It's {amount} that I didn't expect.",
                   "The trial was supposed to end automatically."],
        "agent_q": ["Let me check that subscription. When did you first sign up?",
                    "I understand. Which subscription are we talking about?"],
        "resolve": ["I've cancelled the renewal and refunded {amount} as it was within the cooling-off period.",
                    "The trial was set to auto-renew. I've stopped it and reversed the charge."],
        "also": ["Also, a subscription renewed on my account and I didn't want that.",
                 "And my add-on subscription renewed without my consent."],
        "vague": [],
    },
    "tariff_downgrade": {
        "opener": [
            "I'd like to switch to a cheaper plan, I don't use much data.",
            "Hi, can I downgrade my tariff? The current one is too expensive.",
            "I want to reduce my plan to the smallest one available.",
        ],
        "detail": ["I only use about 2 GB a month.", "Money is tight at the moment, I need to save.",
                   "I'm mostly on Wi-Fi now."],
        "agent_q": ["Sure. How much data do you usually need?", "Let me see which smaller plans are available for you."],
        "resolve": ["I've moved you to the 5 GB plan at {amount} per month from your next billing cycle.",
                    "The downgrade is scheduled; your new lower price starts next month."],
        "also": ["Also, I'd like to move to a cheaper plan.", "And can I lower my tariff? I don't need that much data."],
        "vague": [],
    },
    "overage_charges": {
        "opener": [
            "I was charged extra for going over my data limit, but I never got a warning and I don't think I went over.",
            "Hi, there's a {amount} out-of-bundle data charge on my bill, but my plan should stop when the data runs out.",
        ],
        "detail": ["The app showed I still had data left that day.", "I have the data cap setting turned on."],
        "agent_q": ["Let me check your data usage for that period.", "When was the out-of-bundle charge applied?"],
        "resolve": ["The spending cap wasn't applied correctly; I've removed the {amount} overage charge.",
                    "You're right, the usage should have been blocked. I've credited the charge back."],
        "also": ["Also, I got an extra charge for exceeding my data allowance, which I don't think is right."],
        "vague": [],
    },
    "lost_sim": {
        "opener": [
            "I lost my phone yesterday and need a new SIM card with the same number.",
            "Hi, my SIM card was stolen together with my bag, I need a replacement.",
        ],
        "detail": ["Please block the old SIM so nobody can use it.", "I already reported it to the police."],
        "agent_q": ["I'm sorry to hear that. I'll block the old SIM first. Can you confirm your address?",
                    "Let me secure your line. Do you want the replacement sent to your home address?"],
        "resolve": ["The old SIM is blocked and a replacement with your number will arrive in two working days.",
                    "I've blocked the lost SIM and ordered a replacement free of charge."],
        "also": ["Also, I lost my SIM card and need a replacement."],
        "vague": [],
    },
    "sim_swap": {
        "opener": [
            "I got a new phone and need to switch my physical SIM to an eSIM.",
            "Hi, my new phone needs a nano SIM, can I swap my old SIM for a smaller one?",
        ],
        "detail": ["The phone only supports eSIM in the second slot.", "My current SIM is the old standard size."],
        "agent_q": ["Sure. Do you want an eSIM profile or a physical replacement SIM?",
                    "I can arrange that. Which phone model do you have?"],
        "resolve": ["I've generated an eSIM QR code and sent it to your email; your old SIM will stop working once you scan it.",
                    "A new triple-cut SIM is on its way; your number stays the same."],
        "also": ["And I also want to change my SIM to an eSIM for my new phone."],
        "vague": [],
    },
    "number_porting": {
        "opener": ["I'm switching to you from another provider and want to keep my old number. How does porting work?"],
        "detail": ["My old provider gave me a PAC code already."],
        "agent_q": ["Great to have you! Do you have the porting authorisation code from your old provider?"],
        "resolve": ["I've submitted the port request; your number will transfer within one working day."],
        "also": ["Also, I want to bring my number over from my old provider."],
        "vague": [],
    },
    "address_change": {
        "opener": ["Hi, I moved house and need to update my address on the account."],
        "detail": ["The new address is in {city}, I moved last week."],
        "agent_q": ["Of course. Could you give me the new address and postcode?"],
        "resolve": ["I've updated your address; your next bill will go to the new address."],
        "also": ["Also, please update my address, I've moved."],
        "vague": [],
    },
}

SMALL_TALK = [
    ("Before we start, sorry, it's so loud here, I'm at a football match.", "No problem at all, take your time!"),
    ("Lovely weather today, isn't it? Finally some sunshine.", "It really is! I hope you get to enjoy it later."),
    ("I've been on hold for ages listening to that music, it's stuck in my head now, haha.",
     "Sorry about the wait, and the music! Thanks for your patience."),
    ("How's your day going? Busy I imagine.", "It's been busy, but good, thanks for asking!"),
    ("Sorry, my dog is barking in the background.", "Ha, no worries, I can hear you fine."),
    ("Happy Friday by the way!", "Happy Friday to you too!"),
]

FOLLOW_UPS = [
    ("How long will that take?", "It should be completed within 24 hours."),
    ("Will I get some kind of confirmation?", "Yes, you'll receive an SMS confirmation shortly."),
    ("Do I need to do anything else on my side?", "No, nothing else is needed from you."),
    ("Okay. And this won't happen again?", "I've added a note to your account so we can track it if it does."),
]

GREET = {
    "voice": "Thank you for calling customer service, my name is {agent}. How can I help you today?",
    "whatsapp": "Hi there 👋 You're chatting with {agent} from customer care. What can I do for you?",
    "web_messaging": "Hello, this is {agent}. Thanks for contacting us via chat. How can I help?",
    "social_media": "Hi! Thanks for reaching out. I'm {agent} from the support team, send us a few details and we'll help.",
}
CLOSING_CUSTOMER = ["Great, thank you so much.", "Perfect, thanks for your help.", "Okay, that's all, thanks.",
                    "Thanks, much appreciated.", "Alright, cheers."]
CLOSING_AGENT = ["You're welcome! Is there anything else I can help with?", "Happy to help. Have a great day!",
                 "My pleasure. Thanks for being with us."]
AGENTS = ["Sarah", "Tom", "Priya", "Lukas", "Maria", "James", "Aisha", "Daniel"]
CITIES = ["Northfield", "Riverton", "Lakeside", "Brookhaven", "Millbrook", "Eastwood"]
COUNTRIES = ["Spain", "Turkey", "Switzerland", "the USA", "Italy", "Morocco"]

CHANNELS = [("voice", "prepaid", 25), ("voice", "postpaid", 25), ("whatsapp", None, 20),
            ("web_messaging", None, 18), ("social_media", None, 12)]


def fill(rng: random.Random, text: str) -> str:
    return text.format(
        amount=f"€{rng.choice([9.99, 14.99, 19.99, 24.5, 29.99, 39.99, 49.0, 59.99, 79.99])}",
        country=rng.choice(COUNTRIES), city=rng.choice(CITIES),
        date1=rng.choice(["3rd", "5th", "8th", "12th"]), date2=rng.choice(["15th", "18th", "21st", "27th"]),
        time=rng.choice(["9 am", "lunchtime", "6 pm", "8:30 in the evening"]),
    )


def plan_conversations(rng: random.Random) -> list[list[str]]:
    keys = list(INTENTS)
    occurrences = [k for k in keys for _ in range(INTENTS[k][3])]
    rng.shuffle(occurrences)
    # primary intents: every type at least once, remaining slots filled from the shuffled pool
    primaries = list(keys)
    pool = occurrences.copy()
    for k in keys:
        pool.remove(k)
    extra_needed = N_CONVERSATIONS - len(primaries)
    primaries += pool[:extra_needed]
    secondaries = pool[extra_needed:]
    rng.shuffle(primaries)
    convs = [[p] for p in primaries]

    def segment_of(intents: list[str]) -> str | None:
        segs = {INTENTS[i][4] for i in intents} - {None}
        return segs.pop() if len(segs) == 1 else (None if not segs else "conflict")

    for s in secondaries:
        for _ in range(200):
            c = rng.choice(convs)
            if s in c or len(c) >= 3 or (len(c) == 2 and rng.random() < 0.85):
                continue
            if segment_of(c + [s]) == "conflict":
                continue
            c.append(s)
            break
    return convs


def build_conversation(rng: random.Random, idx: int, intents: list[str], channel: str, segment: str,
                       small_talk: bool, ambiguous: bool) -> tuple[dict, list[str]]:
    agent = rng.choice(AGENTS)
    short = channel != "voice" and len(intents) == 1 and not small_talk and rng.random() < 0.3
    turns = [] if short else [{"speaker": "agent", "text": GREET[channel].format(agent=agent)}]
    tags = []
    if small_talk:
        st = rng.choice(SMALL_TALK)
        turns += [{"speaker": "customer", "text": st[0]}, {"speaker": "agent", "text": st[1]}]
        tags.append("small_talk")
    first = T[intents[0]]
    if ambiguous and first["vague"]:
        opener = rng.choice(first["vague"])
        tags.append("ambiguous")
    else:
        opener = rng.choice(first["opener"])
    turns.append({"speaker": "customer", "text": fill(rng, opener)})
    turns.append({"speaker": "agent", "text": fill(rng, rng.choice(first["agent_q"]))})
    turns.append({"speaker": "customer", "text": fill(rng, rng.choice(first["detail"]))})
    turns.append({"speaker": "agent", "text": fill(rng, rng.choice(first["resolve"]))})
    if short:
        return {"turns": turns}, tags
    if rng.random() < 0.35:
        turns += [{"speaker": s, "text": t} for s, t in zip(("customer", "agent"), rng.choice(FOLLOW_UPS))]
    for extra in intents[1:]:
        tp = T[extra]
        turns.append({"speaker": "customer", "text": fill(rng, rng.choice(tp["also"]))})
        if rng.random() < 0.6:
            turns.append({"speaker": "agent", "text": fill(rng, rng.choice(tp["agent_q"]))})
            turns.append({"speaker": "customer", "text": fill(rng, rng.choice(tp["detail"]))})
        turns.append({"speaker": "agent", "text": fill(rng, rng.choice(tp["resolve"]))})
    if len(intents) > 1:
        tags.append("multi_intent")
    if rng.random() < 0.7 or len(turns) < 6:
        turns.append({"speaker": "customer", "text": rng.choice(CLOSING_CUSTOMER)})
        turns.append({"speaker": "agent", "text": rng.choice(CLOSING_AGENT)})
    return {"turns": turns[:12]}, tags


def generate() -> tuple[list[dict], dict]:
    rng = random.Random(SEED)
    convs = plan_conversations(rng)
    channel_slots = [(ch, seg) for ch, seg, n in CHANNELS for _ in range(n)]
    rng.shuffle(channel_slots)
    ambiguous_idx = set(rng.sample([i for i, c in enumerate(convs) if T[c[0]]["vague"]], 6))
    small_talk_idx = set(rng.sample(range(N_CONVERSATIONS), 12))
    start = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    transcripts, truth = [], []
    for i, intents in enumerate(convs):
        need = {INTENTS[k][4] for k in intents} - {None}
        need_seg = need.pop() if need else None
        # pick a channel slot compatible with the required segment
        slot_i = next((j for j, (_, seg) in enumerate(channel_slots) if need_seg is None or seg in (None, need_seg)), None)
        if slot_i is None:
            channel, seg = channel_slots.pop(0)
            seg = None
        else:
            channel, seg = channel_slots.pop(slot_i)
        segment = seg or need_seg or rng.choice(["prepaid", "postpaid"])
        body, tags = build_conversation(rng, i, intents, channel, segment, i in small_talk_idx, i in ambiguous_idx)
        cid = f"TELCO-{i + 1:04d}"
        ts = start + timedelta(minutes=rng.randint(0, 45 * 24 * 60))
        queue = {"voice": f"{segment.capitalize()} Support", "whatsapp": "WhatsApp Care", "web_messaging": "Web Chat",
                 "social_media": "Social Care"}[channel]
        transcripts.append({"conversation_id": cid, "channel": channel, "segment": segment, "language": "en",
                            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "queue": queue, "turns": body["turns"]})
        truth.append({"conversation_id": cid, "tags": tags,
                      "intents": [{"key": k, "label": INTENTS[k][0], "l1_id": INTENTS[k][1], "l2_id": INTENTS[k][2]}
                                  for k in intents]})
    gt = {"seed": SEED, "note": "Ground truth for evaluation only. Never provided to the analysis pipeline.",
          "intent_types": [{"key": k, "label": v[0], "l1_id": v[1], "l2_id": v[2]} for k, v in INTENTS.items()],
          "conversations": truth}
    return transcripts, gt


def write(out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    transcripts, gt = generate()
    (out / "sample_transcripts.json").write_text(json.dumps(transcripts, indent=2, ensure_ascii=False) + "\n")
    (out / "sample_ground_truth.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False) + "\n")
    with (out / "sample_transcripts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["conversation_id", "channel", "segment", "language", "timestamp", "queue", "transcript"])
        for t in transcripts:
            text = "\n".join(f"{'Customer' if x['speaker'] == 'customer' else 'Agent'}: {x['text']}" for x in t["turns"])
            w.writerow([t["conversation_id"], t["channel"], t["segment"], t["language"], t["timestamp"], t["queue"], text])
    with (out / "import_template.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["conversation_id", "channel", "segment", "language", "timestamp", "queue", "transcript"])
        w.writerow(["CONV-0001", "voice", "prepaid", "en", "2026-10-20T10:00:00Z", "Prepaid Support",
                    "Customer: I topped up yesterday but the credit is missing.\nAgent: I can check the transaction for you."])
        w.writerow(["CONV-0002", "whatsapp", "postpaid", "en", "2026-10-20T11:30:00Z", "WhatsApp Care",
                    "Agent: Hi, how can I help?\nCustomer: My bill shows the monthly fee twice."])
    n_intents = sum(len(c["intents"]) for c in gt["conversations"])
    tags = {}
    for c in gt["conversations"]:
        for t in c["tags"]:
            tags[t] = tags.get(t, 0) + 1
    print(f"Wrote {len(transcripts)} conversations, {n_intents} intents, {len(INTENTS)} intent types, tags={tags} → {out}")


if __name__ == "__main__":
    write()
