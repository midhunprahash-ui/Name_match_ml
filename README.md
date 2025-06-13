> [!NOTE]\
> The `MODEL_TRAINING`, `TRAINED_MODELS`, and related ML files in this repository represent an alternative approach I explored using machine learning to solve the username matching use case. However, after experimentation, I found that traditional string matching algorithms (fuzzy and phonetic matching) deliver more accurate and interpretable results for this specific problem.

> Hence, the core files of this project are:
	•	`main.py`
	•	`employee_data.csv`
	•	`templates`/ folder

*The ML components are included in the repo for reference only, as part of the experimentation process.*
---


# 🔍 Username Matching System

This project is a **Flask web application** that takes a username input and predicts the most likely employee(s) it belongs to using intelligent fuzzy matching and phonetic similarity.

---

## 🔁 About This Project

This project is a follow-up to my earlier work on username matching using purely machine learning techniques. In that version, I trained models to classify username-employee pairings based on engineered features like string similarity scores and phonetic distances. While promising, the ML-based approach introduced complexity and opacity that made it harder to justify for a use case rooted in pattern recognition and linguistic intuition.

**This version aims to simplify the process while improving performance** by leaning entirely on traditional methods such as:
- Fuzzy string matching
- Phonetic algorithms
- Rule-based heuristics

It turns out that, for this use case, traditional algorithms not only yield comparable or better accuracy but also keep the logic explainable and easily modifiable.

---

## 🚀 Features

- Match usernames against employee data using:
  - **Fuzzy string matching** (`thefuzz`)
  - **Phonetic algorithms** (`jellyfish` - Soundex, Metaphone)
  - **Heuristics** (e.g., `emp_id` presence in username)
- Categorized ranking with labels:
  - **TOP MATCH** (highest confidence)
  - **BEST MATCH** (next highest)
  - **NOT SURE** (lower confidence)
- Clean Flask web UI for input and results
---

## 🧠 Tech Stack

| Component     | Technology        |
|---------------|-------------------|
| Backend       | Python 3, Flask   |
| Matching Algo | thefuzz, jellyfish|
| Frontend      | HTML (via Jinja)  |
| Data Handling | pandas            |

---

## 📊 Employee CSV Format

Your `employee_data.csv` should include the following columns:

| emp_id | first_name | last_name |
|--------|------------|-----------|
| 101    | Alice      | Johnson   |
| 102    | Bob        | Smith     |

> [!NOTE]\
> You must generate a sample `employee_data.csv` file and save it to your project folder in the format given above to use the application, or use the `employee_data.csv` file uploaded in the repo.

---

![Sample Output](assets/output_example.png)

___

## 🛠️ Setup & Installation

1. **Clone the repository**
```bash
git clone https://github.com/your-username/username-matching-app.git
cd username-matching-app
```
2. **Create Virtual Environment**
```
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```
3. **Install Dependencies**
```
pip install -r requirements.txt
```
4. **Run the app**

```
python main.py
```
