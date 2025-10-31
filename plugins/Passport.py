# ... imports and constants same as before ...

class PassportPlugin(QWidget):
    def __init__(self):
        super().__init__()

        # Load JSON
        self.load_json_data()

        # Fullscreen and frameless
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()

        # ---------------------- Background as QLabel ----------------------
        bg_path = os.path.join(plugin_folder, "passport.png")
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.bg_label.setPixmap(pixmap)
        self.bg_label.lower()  # ensure everything else is on top

        # ---------------------- Name ----------------------
        self.name_label = QLabel(self)
        self.name_label.setFont(QFont("Arial", 60))
        self.name_label.setText(self.rebecca_data.get("name", {}).get("firstname", "Unknown"))
        self.name_label.move(NAME_X, NAME_Y)
        self.name_label.setFixedWidth(self.width())
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------------- Mood ----------------------
        self.mood_label = QLabel(self)
        self.mood_label.setFont(QFont("Arial", 60))
        self.mood_label.setText(f"Mood: {self.rebecca_xp.get('mood', 'Neutral')}")
        self.mood_label.move(MOOD_X, MOOD_Y)
        self.mood_label.setFixedWidth(self.width())
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------------- Level ----------------------
        self.level_label = QLabel(self)
        self.level_label.setFont(QFont("Arial", 60))
        self.level_label.setText(f"Level: {self.rebecca_xp.get('level', 0)}")
        self.level_label.move(LEVEL_X, LEVEL_Y)
        self.level_label.setFixedWidth(self.width())
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------------- XP Bar ----------------------
        self.progress = QProgressBar(self)
        self.progress.setGeometry(PROGRESS_X, PROGRESS_Y, PROGRESS_W, PROGRESS_H)
        self.progress.setMaximum(LEVELS[-1])
        self.progress.setValue(self.rebecca_xp.get("xp", 0))
        self.progress.setFormat("XP: %v/%m")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 3px solid #000;
                border-radius: 15px;
                background-color: #9CED21;
                text-align: center;
                font: 24px 'Arial';
                color: white;
            }
            QProgressBar::chunk {
                border-radius: 15px;
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #47CC00, stop:1 #3D8F11
                );
            }
        """)

        # ---------------------- Face Frame ----------------------
        self.face_label = QLabel(self)
        self.face_label.setGeometry(FRAME_X, FRAME_Y, FRAME_W, FRAME_H)
        self.face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_label.setStyleSheet("border-radius: 15px;")

        self.face_images = self.load_face_images()
        self.face_cycle = cycle(self.face_images)
        self.update_face()

        # Face Timer
        self.face_timer = QTimer()
        self.face_timer.timeout.connect(self.update_face)
        self.face_timer.start(1000)

    # JSON loading, face animation, update_face, and ESC key remain the same
