import nbformat
from nbconvert.preprocessors import ExecutePreprocessor
import os

print("Starting local notebook execution...")

with open('VoltRelay_Data_Analytics_Hackathon.ipynb', 'r', encoding='utf-8') as f:
    nb = nbformat.read(f, as_version=4)

# In cell 1, adjust code so it runs cleanly in Python
# Let's check cell 1
for cell in nb.cells:
    if cell.cell_type == 'code':
        # Remove ! lines for local execution or handle them
        lines = []
        for line in cell.source.split('\n'):
            if line.strip().startswith('!'):
                # comment out shell commands during execution if packages exist
                lines.append('# ' + line)
            else:
                lines.append(line)
        cell.source = '\n'.join(lines)

ep = ExecutePreprocessor(timeout=600, kernel_name='python3')

try:
    ep.preprocess(nb, {'metadata': {'path': '.'}})
    print("Notebook executed successfully without errors!")
    
    # Restore the !pip install lines in cell 0 so Colab users can see them
    for cell in nb.cells:
        if cell.cell_type == 'code' and '!pip' in cell.source:
            cell.source = cell.source.replace('# !pip', '!pip').replace('# !gdown', '!gdown')
            break

    with open('VoltRelay_Data_Analytics_Hackathon.ipynb', 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)
    print("Pre-executed notebook saved with all outputs embedded!")
except Exception as e:
    print("Execution Error:", e)
    import traceback
    traceback.print_exc()
