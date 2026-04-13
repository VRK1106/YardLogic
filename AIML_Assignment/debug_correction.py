
def correct_plate_format(text: str) -> str | None:
    """
    Copy of the logic from vision.py for debugging
    """
    # Clean cleanup first
    text = ''.join(e for e in text if e.isalnum()).upper()
    print(f"Cleaned Text: {text} (Len: {len(text)})")
    
    # Mappings
    text_to_digit = {'O': '0', 'Q': '0', 'D': '0', 'U': '0', 'I': '1', 'L': '1', 'Z': '2', 'S': '5', 'G': '6', 'B': '8', 'A': '4'}
    digit_to_text = {'0': "O", '1': 'I', '2': 'Z', '5': 'S', '6': 'G', '8': 'B', '4': 'A'}
    
    structure = [True, True, False, False, True, True, False, False, False, False]
    
    candidates = []
    
    # If length match (10), try direct correction
    if len(text) == 10:
        candidates.append(text)
    
    # If longer (11-12), try sliding window of 10
    elif len(text) > 10 and len(text) <= 13:
        for i in range(len(text) - 9):
            candidates.append(text[i : i+10])
            
    # Also try "IND" removal if not already handled
    if text.startswith("IND") and len(text) > 3:
            sub = text[3:]
            if len(sub) >= 10:
                print(f"Adding IND candidate: {sub[:10]}")
                candidates.append(sub[:10])

    print(f"Candidates: {candidates}")

    best_score = -1
    best_corrected = None
    
    for idx, candidate in enumerate(candidates):
        print(f"Checking Candidate {idx}: {candidate}")
        current_corrected = []
        score = 0
        valid = True
        
        for i, char in enumerate(candidate):
            expect_text = structure[i]
            
            if expect_text: # Indices 0,1, 4,5
                if char.isalpha():
                    current_corrected.append(char)
                    score += 1 # Perfect match
                    print(f"  [{i}] {char} -> OK (Text)")
                elif char.isdigit():
                    if char in digit_to_text:
                        fixed = digit_to_text[char]
                        current_corrected.append(fixed)
                        score += 0.8 # Corrected match
                        print(f"  [{i}] {char} -> Fixed to {fixed}")
                    else:
                        print(f"  [{i}] {char} -> FAIL (Digit in Text pos, no mapping)")
                        valid = False; break # Unfixable
                else:
                     valid = False; break
            else: # Expect Digit # Indices 2,3, 6,7,8,9
                if char.isdigit():
                    current_corrected.append(char)
                    score += 1 # Perfect match
                    print(f"  [{i}] {char} -> OK (Digit)")
                elif char.isalpha():
                    # Explicit user rule: Q -> 0 in number slots
                    if char == 'Q':
                        current_corrected.append('0')
                        score += 0.9
                        print(f"  [{i}] Q -> Fixed to 0")
                    elif char in text_to_digit:
                        fixed = text_to_digit[char]
                        current_corrected.append(fixed)
                        score += 0.8 # Corrected match
                        print(f"  [{i}] {char} -> Fixed to {fixed}")
                    else:
                        print(f"  [{i}] {char} -> FAIL (Text in Digit pos, no mapping)")
                        valid = False; break # Unfixable
                else:
                    valid = False; break
        
        if valid:
            print(f"  VALID. Score: {score}")
            if score > best_score:
                best_score = score
                best_corrected = "".join(current_corrected)
        else:
            print("  INVALID")
            
    if best_corrected:
        final = best_corrected
        return f"{final[:2]} {final[2:4]} {final[4:6]} {final[6:]}"
        
    return None

# Test Case
test_str = "HRZSDK83371"
print(f"Input: {test_str}")
result = correct_plate_format(test_str)
print(f"Result: {result}")
