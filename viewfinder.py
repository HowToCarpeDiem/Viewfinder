import sys
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QFileDialog
from PySide6.QtGui import QImage, QPixmap
import cv2


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.ly1 = QVBoxLayout()
        self.setLayout(self.ly1)

        self.lb_image = QLabel('Image')
        self.ly1.addWidget(self.lb_image)
        self.btn_load = QPushButton('Load image')
        self.ly1.addWidget(self.btn_load)
        self.btn_load.clicked.connect(self.load_image)


    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images ( *.png *.jpg)")
        if file_path:
            print(file_path)
            img_bgr = cv2.imread(file_path)
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            img = QPixmap.fromImage(q_img)
            self.lb_image.setPixmap(img)
            

app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()