# styles.py
APP_QSS = r"""
/* ---------- App background ---------- */
#root {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #0B1220,
        stop:1 #111827
    );
}

/* ---------- Cards ---------- */
#card {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 22px;
    min-width: 440px;
}

#cardWide {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 22px;
    min-width: 700px;
    max-width: 900px;
}

/* ---------- Titles ---------- */
#title {
    color: #E5E7EB;
    font-size: 36px;
    font-weight: 900;
}

#subtitle {
    color: rgba(229, 231, 235, 0.70);
    font-size: 14px;
}

#hint {
    color: rgba(229, 231, 235, 0.55);
    font-size: 12px;
}

/* ---------- Buttons ---------- */
QPushButton {
    border-radius: 14px;
    font-size: 14px;
    font-weight: 800;
    padding: 12px;
}

#btnPrimary {
    background: #3B82F6;
    color: #0B1220;
}

#btnPrimaryAlt {
    background: #22C55E;
    color: #052e16;
}

#btnSecondary {
    background: rgba(255, 255, 255, 0.12);
    color: #E5E7EB;
}

#btnGhost {
    background: rgba(255, 255, 255, 0.05);
    color: rgba(229, 231, 235, 0.85);
}

/* ---------- Tabs ---------- */
QTabWidget#tabs::pane {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    top: -1px;
}

QTabBar::tab {
    background: rgba(255,255,255,0.06);
    padding: 10px 14px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    color: rgba(229,231,235,0.85);
    margin-right: 6px;
}

QTabBar::tab:selected {
    background: rgba(255,255,255,0.12);
    color: #E5E7EB;
}

/* ---------- Dialog ---------- */
#dlgCard {
    background: rgba(17, 24, 39, 235);
    border-radius: 16px;
}

#dlgTitle {
    color: #E5E7EB;
    font-size: 18px;
    font-weight: 900;
}

#dlgSub {
    color: rgba(229, 231, 235, 0.70);
    font-size: 12px;
}

#dlgHint {
    color: rgba(229, 231, 235, 0.55);
    font-size: 11px;
    margin-top: 6px;
}

/* ---------- Inputs ---------- */
QComboBox#combo {
    padding: 6px 10px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.10);
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

QComboBox#combo::drop-down {
    border: none;
}

QComboBox#combo QAbstractItemView {
    background: #111827;
    color: #E5E7EB;
    selection-background-color: rgba(59, 130, 246, 0.35);
}

QSpinBox#spin {
    padding: 6px 10px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.10);
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

QLineEdit, QPlainTextEdit, QListWidget {
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.08);
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.12);
}
"""
