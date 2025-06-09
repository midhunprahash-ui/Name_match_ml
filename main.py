from flask import Flask, render_template, request
import pandas as pd
from thefuzz import fuzz
import jellyfish
import  re

app = Flask(__name__)

def compute_match_score(username, full_name, first_name, last_name, emp_id):

    numbers_in_username = re.findall(r'\d+', username)
    number_match_bonus = 0
    if numbers_in_username:
       
        if str(emp_id) in numbers_in_username:
            number_match_bonus = 15 
    
    lev_full = fuzz.ratio(username, full_name)
    partial_full = fuzz.partial_ratio(username, full_name)
    token_set_full = fuzz.token_set_ratio(username, full_name)
    

    lev_first = fuzz.ratio(username, first_name)
    partial_first = fuzz.partial_ratio(username, first_name)
    token_set_first = fuzz.token_set_ratio(username, first_name)
    
    
    lev_last = fuzz.ratio(username, last_name)
    partial_last = fuzz.partial_ratio(username, last_name)
    token_set_last = fuzz.token_set_ratio(username, last_name)
    
    soundex_match_full = int(jellyfish.soundex(username) == jellyfish.soundex(full_name))
    metaphone_match_full = int(jellyfish.metaphone(username) == jellyfish.metaphone(full_name))
    soundex_match_last = int(jellyfish.soundex(username) == jellyfish.soundex(last_name))
    metaphone_match_last = int(jellyfish.metaphone(username) == jellyfish.metaphone(last_name))
    soundex_match_first = int(jellyfish.soundex(username) == jellyfish.soundex(first_name))
    metaphone_match_first = int(jellyfish.metaphone(username) == jellyfish.metaphone(first_name))
    
    
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)
    
    
    composite = (
        (max_lev * 0.4) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 10) +
        (metaphone_match_last * 10) +
        (soundex_match_first * 10) +  
        (metaphone_match_first * 10)+
        (soundex_match_full * 10) +  
        (metaphone_match_full * 10)+
        number_match_bonus
    )
    return min(composite, 100)

def fetch_employees():
    try:
        df = pd.read_csv('employee_data.csv')
        df.columns = df.columns.str.lower()
        if {'emp_id', 'first_name', 'last_name'}.issubset(df.columns):
            df['employee_name'] = df['first_name'].str.strip() + ' ' + df['last_name'].str.strip()
            return df[['emp_id', 'employee_name', 'first_name', 'last_name']]
    except Exception as e:
        print(f"Error: {e}")
    return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

@app.route('/', methods=['GET', 'POST'])
def index():
    matches = []
    top_matches = []
    input_username = ""

    if request.method == 'POST':
        input_username = request.form['username'].strip().lower()
        employees = fetch_employees()

        if not employees.empty:
            employees['score'] = employees.apply(
                lambda row: compute_match_score(
                    input_username,
                    row['employee_name'].lower(),
                    row['first_name'].lower(),
                    row['last_name'].lower(),
                    row['emp_id']
                ), axis=1
            )

            
            matches_df = employees[employees['score'] >= 65]\
                .sort_values('score', ascending=False)

            
            excluded_ids = set(matches_df['emp_id'])
            top_matches_df = employees[~employees['emp_id'].isin(excluded_ids)]\
                .sort_values('score', ascending=False)\
                .head(5)

            
            matches = matches_df.to_dict(orient='records')
            top_matches = top_matches_df.to_dict(orient='records')

    return render_template(
        'index.html',
        matches=matches,
        top_matches=top_matches,
        input_username=input_username
    )



if __name__ == '__main__':
    app.run(debug=True)
