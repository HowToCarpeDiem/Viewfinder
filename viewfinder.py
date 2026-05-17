import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QFileDialog
from PySide6.QtGui import QImage, QPixmap, QAction
from PySide6.QtCore import Qt
import cv2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.img_bgr = None
        self.img_current = None

        #Przestrzeń
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        #Główne okno
        self.ly_main = QHBoxLayout()
        central_widget.setLayout(self.ly_main)

        #Lewy panel
        self.ly_left = QVBoxLayout()
        self.ly_main.addLayout(self.ly_left)

        #Prawy panel
        self.ly_right = QVBoxLayout()
        self.ly_main.addLayout(self.ly_right)

        #Pasek
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('File')

        #Zapis obrazu - pasek
        save_action = QAction('Save', self)
        file_menu.addAction(save_action)
        save_action.triggered.connect(self.save_image)

        #Wczytanie obrazu - pasek
        load_action = QAction('Open', self)
        file_menu.addAction(load_action)
        load_action.triggered.connect(self.load_image)

        #Miejsce na obraz
        self.lb_image = QLabel('Image')
        self.ly_right.addWidget(self.lb_image)

        #Przycisk wczytywania obrazu
        # self.btn_load = QPushButton('Load image')
        # self.ly_left.addWidget(self.btn_load)
        # self.btn_load.clicked.connect(self.load_image)

        #Skala szarości
        self.btn_grayscale = QPushButton('Grayscale')
        self.ly_left.addWidget(self.btn_grayscale)
        self.btn_grayscale.clicked.connect(self.apply_grayscale)


    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images ( *.png *.jpg)")
        if file_path:
            print(file_path)
            self.img_bgr = cv2.imread(file_path)
            self.img_current = self.img_bgr.copy()
            img_rgb = cv2.cvtColor(self.img_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            img = QPixmap.fromImage(q_img)
            img_scaled = img.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lb_image.setPixmap(img_scaled)


    def apply_grayscale(self):
        if self.img_bgr is not None:
            img_gray = cv2.cvtColor(self.img_bgr, cv2.COLOR_BGR2GRAY)
            h, w = img_gray.shape
            bytes_per_line = w
            q_img = QImage(img_gray.data, w, h, bytes_per_line, QImage.Format_Grayscale8)
            img = QPixmap.fromImage(q_img)
            img_scaled = img.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lb_image.setPixmap(img_scaled)
            self.img_current = img_gray


    def save_image(self):
        if self.img_current is not None:
            file_path, _ = QFileDialog.getSaveFileName(self, 'Save image', '', 'Images (*.png *.jpg)')
            if file_path:
                cv2.imwrite(file_path, self.img_current)
        else:
            print("First, load image")


app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()