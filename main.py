import os
import sys

# Garante que a pasta src seja reconhecida como módulo
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.gui import App

if __name__ == '__main__':
    app = App()
    app.mainloop()