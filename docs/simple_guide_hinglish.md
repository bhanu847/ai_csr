# Ye App Kya Hai — Bilkul Simple Bhasha Mein

Ye file isliye hai taaki koi bhi bacha bhi samajh jaaye ki ye app kya karta hai. Koi mushkil word nahi, bas simple Hinglish.

---

## 1. Sabse Pehle — Ye App Hai Kya?

Socho ek **robot receptionist** hai jo phone uthata hai. Jab koi customer call karta hai, ye robot (AI) baat karta hai bilkul insaan jaisa — sunta hai, samajhta hai, aur jawab deta hai. Ye khaas taur pe **pharmacy/health insurance** wale calls ke liye bana hai — jaise "meri dawai ka status kya hai," "mera claim approve hua ya nahi," "nearest pharmacy kaunsi hai."

Sabse important baat: ye robot **jhoot nahi bolta**. Agar usko pata nahi hai, to seedha bol dega "mujhe nahi pata, main insaan se connect karta hoon" — guess nahi karega.

---

## 2. Jab Koi Call Karta Hai — Poori Kahani

```
Customer phone milata hai
        │
        ▼
Twilio (jo phone line ka kaam karta hai) call ko
        hamare computer (backend) tak pahunchata hai
        │
        ▼
Robot "Hello!" bolta hai (agar customer purana hai to naam se bulata hai)
        │
        ▼
Customer kuch poochta hai ("mera claim status kya hai?")
        │
        ▼
Azure Speech ye awaaz ko TEXT mein badalta hai (jaise likhna)
        │
        ▼
Azure OpenAI (ye AI ka dimaag hai) sochta hai:
   "Iska jawab dene ke liye mujhe kya karna padega?"
   - Kya document check karna hai?
   - Kya database se claim dekhna hai?
   - Pehle identity verify karni hai kya?
        │
        ▼
Robot sahi jawab banata hai
        │
        ▼
Azure Speech us jawab ko wapas AWAAZ mein badalta hai
        │
        ▼
Customer robot ki awaaz sunta hai — bilkul insaan jaisi
        │
        ▼
Call khatam → sab kuch save ho jaata hai
   (summary, kitna accha jawab tha, sab likh liya jaata hai)
```

**Ek cool cheez:** agar customer beech mein bolna shuru kar de jab robot bol raha ho, robot **turant chup ho jaata hai** aur sunna shuru kar deta hai — bilkul jaise ek achha insaan karta hai. Isko "barge-in" bolte hain.

---

## 3. Kaun Kaun Se "Magic Tools" Use Hote Hain

| Tool | Iska Kaam Kya Hai | Simple Example |
|---|---|---|
| **Twilio** | Phone line deta hai — jaise ek SIM card | Isi wajah se real number pe call kar sakte ho |
| **Azure OpenAI** | Robot ka dimaag — sochta hai kya bolna hai | Jaise ek bahut smart dost jo sab kuch samajh leta hai |
| **Azure Speech** | Kaan aur muh — sunta hai aur bolta hai | Awaaz ↔ Text badalta hai dono taraf |
| **Ollama (Database ke liye)** | Documents ko "yaad" rakhta hai search ke liye | Jaise ek library ka index card system |
| **Database (Postgres)** | Sab kuch yahin store hota hai | Jaise ek bada locked cupboard, har company ka apna khaana |

---

## 4. Har Page Ka Kaam (Ekdum Simple)

- **Dashboard** — Aaj kitni calls hui, kitni sahi se solve hui — ek nazar mein sab dikh jaata hai
- **Agent Studio** — Yahan tum apna robot banate ho — naam do, awaaz choose karo, documents upload karo taaki wo unse seekh sake
- **Live Operations** — Abhi jo calls chal rahi hain unko live dekh sakte ho, chaho to robot ko rok bhi sakte ho
- **Conversations** — Purani sab calls ki poori baatcheet padh sakte ho
- **Customers** — Jo bhi kabhi call kiya hai, unki list aur history
- **Workflows** — "Jab ye ho, to ye karo" wale rules bana sakte ho, bina coding ke
- **Analytics** — Graphs — log kis baare mein sabse zyada poochte hain
- **AI Training** — Robot khud dekh ta hai ki kahan galti ho rahi hai aur sujhaav deta hai
- **Data Import** — Bahut sara data (jaise Excel file) ek saath upload kar sakte ho

---

## 5. Robot Jhoot Kyun Nahi Bolta (Confidence Engine)

Jab robot ko document mein se jawab dhoondhna hota hai, wo pehle apne aap se poochta hai: **"Mujhe ye jawab kitna sach lagta hai — 0 se 100 mein?"**

- Agar score **75 ya usse zyada** → confident jawab de deta hai
- Agar score **53 se 74 ke beech** → jawab deta hai par bolta hai "ye confirm kar lena"
- Agar score **53 se kam** → seedha bolta hai "mujhe pata nahi, insaan se baat karo"

Ye bilkul waise hai jaise ek achha student exam mein: agar pakka pata hai to answer likhta hai, thoda doubt hai to "shayad" bolta hai, bilkul nahi pata to blank chhod deta hai — guess nahi marta.

**Ek real kahani:** hamne isi hafte (22 August 2026) pehli real call ki, aur robot ne 2 sawaalon ka jawab nahi diya jabki uske paas answer tha! Humne check kiya to pata chala uska "confidence score" thoda kam calculate ho raha tha — jaise ek strict teacher jo bahut zyada marks kaat raha tha. Humne real data se check karke ye number thik kiya. Isse pata chalta hai — hum guess nahi karte, hum test karke fix karte hain.

---

## 6. Security — Har Company Ka Apna Locked Room

Ye app ek saath kai companies (tenants) ke liye kaam kar sakta hai. Har company ka data ek **alag locked room** mein hai — aur ye lock database ke andar hi hai, sirf app code mein nahi. Matlab agar kisi coder se galti bhi ho jaaye, tab bhi ek company ka data doosri company ko nahi dikh sakta. Ye extra safe hai.

Health-related information (jaise claim, benefits) dikhane se pehle robot **hamesha identity verify karta hai** — member ID + date of birth + zip code. Ye rule code mein pakka likha hai, robot ise skip nahi kar sakta chaahe kitna bhi convince kiya jaaye.

---

## 7. Kya Pakka Sach Hai, Kya Abhi Pata Nahi (Bilkul Honest Baat)

| Cheez | Sach Mein Hua? |
|---|---|
| Real call ho sakti hai aur robot jawab deta hai | ✅ Haan, test kiya, kaam karta hai |
| Identity verify kiye bina sensitive info nahi milti | ✅ Haan, test kiya |
| Ek dusre se alag tool badla ja sakta hai (dusra database) | ✅ Haan, test kiya |
| Har sawaal ka sahi jawab deta hai (bahut saari real calls pe) | ❓ Abhi pata nahi — sirf 1 real call hui hai |
| Ek call ka kharcha kitna hai | ❓ Andaza hai, pakka pata nahi |
| Ek saath kitni calls handle kar sakta hai | ❓ Kabhi test nahi kiya |
| Koi real customer isko lena chahta hai | ❓ Abhi tak kisi se baat nahi hui |

Iska matlab: jo bana hai wo sach mein bana hai aur kaam karta hai — lekin "bahut saari calls pe kitna accha hai" ye abhi prove nahi hua. Aur ye baat chhupayi nahi ja rahi — yehi is poore project ka rule hai: **jab tak test na ho, "pata nahi" bolo, "shayad accha hoga" mat bolo.**

---

## 8. Ek Line Mein Sab Kuch

Ye ek robot hai jo phone pe baat karta hai, sach bolta hai, kisi ki private jaankari chori nahi hone deta, aur jab confuse ho to insaan ko bula leta hai — aur jo bhi claim karte hain, usko test karke hi karte hain, sirf bolke nahi.
