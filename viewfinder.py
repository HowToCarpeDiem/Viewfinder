import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QFileDialog, QStackedWidget, QSlider
from PySide6.QtGui import QImage, QPixmap, QAction, QIcon, QPainter, QPen
from PySide6.QtCore import Qt, Signal
import cv2


class InteractiveLabel(QLabel):
    roi_selected = Signal(int, int, int, int)
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.x_start = None
        self.y_start = None
        self.x_end = None
        self.y_end = None
        self.is_drawing = False


    def mousePressEvent(self, event):
        self.is_drawing = True
        self.x_start = event.pos().x()
        self.y_start = event.pos().y()


    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.x_end = event.pos().x()
            self.y_end = event.pos().y()
            self.update()

    
    def mouseReleaseEvent(self, event):
        self.x_end = event.pos().x()
        self.y_end = event.pos().y()
        self.is_drawing = False

        x_rect = min(self.x_start, self.x_end)
        y_rect = min(self.y_start, self.y_end)
        w = abs(self.x_start - self.x_end)
        h = abs(self.y_start - self.y_end)

        self.roi_selected.emit(x_rect, y_rect, w, h)
        self.update()
    
    
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.x_start is not None and self.x_end is not None:
            painter = QPainter(self)
            pen = QPen(Qt.red, 2, Qt.SolidLine)
            painter.setPen(pen)

            x_rect = min(self.x_start, self.x_end)
            y_rect = min(self.y_start, self.y_end)
            w = abs(self.x_start - self.x_end)
            h = abs(self.y_start - self.y_end)
            painter.drawRect(x_rect, y_rect, w, h)


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

        #Górne okno, lewego panelu - pasek narzędzi
        self.ly_tools = QHBoxLayout()
        self.ly_left.addLayout(self.ly_tools)

        #Dolne okno, lewego panelu - ustawienia narzędzi
        self.tool_options = QStackedWidget()
        self.ly_left.addWidget(self.tool_options)

        #Pusty lewy panel
        self.tools_options_default = QWidget()
        ly_tools_options_default = QVBoxLayout()

        self.tools_options_default.setLayout(ly_tools_options_default)
        ly_tools_options_default.addWidget(QLabel('Choose tool'))
        self.tool_options.addWidget(self.tools_options_default)

        #Panel dla grayscale
        self.grayscale = QWidget()
        ly_grayscale = QVBoxLayout()

        self.grayscale.setLayout(ly_grayscale)
        self.tool_options.addWidget(self.grayscale)

        #Panel dla blur
        self.blur = QWidget()
        ly_blur = QVBoxLayout()

        self.blur.setLayout(ly_blur)
        self.tool_options.addWidget(self.blur)

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
        self.lb_image = InteractiveLabel('Image')
        self.ly_right.addWidget(self.lb_image)

        #Pasek narzędzi - grayscale (tool1)
        self.btn_tools1 = QPushButton()
        self.btn_tools1.setIcon(QIcon('assets/grayscale.png'))
        self.ly_tools.addWidget(self.btn_tools1)
        self.btn_tools1.clicked.connect(self.open_tools1_panel)

        #Paske narzędzi - blur
        self.btn_blur = QPushButton()
        self.btn_blur.setIcon(QIcon('assets/blur.png'))
        self.ly_tools.addWidget(self.btn_blur)
        self.btn_blur.clicked.connect(self.open_blur_page)
        
        #ToolsOptions - Grayscale
        self.btn_grayscale = QPushButton('Grayscale')
        ly_grayscale.addWidget(self.btn_grayscale)
        self.btn_grayscale.clicked.connect(self.apply_grayscale)

        #ToolsOptions - blur, slider value
        self.slider_blur = QSlider(Qt.Horizontal)
        self.slider_blur.setRange(1,30)
        ly_blur.addWidget(QLabel('Brush size:'))
        ly_blur.addWidget(self.slider_blur)

        #ToolsOptions - blur, button
        # self.btn_blur = QPushButton('Accept Blur')
        # ly_blur.addWidget(self.btn_blur)

        #Blur
        self.lb_image.roi_selected.connect(self.apply_blur)


    def apply_blur(self, x, y, w, h):
        real_h, real_w, real_ch = self.img_current.shape
        print(real_h)
        print(real_w)
        print(x, y, w ,h)

        disp_w = self.lb_image.pixmap().width()
        disp_h = self.lb_image.pixmap().height()

        ratio_x = real_w/disp_w
        ratio_y = real_h/disp_h

        real_x = int(x*ratio_x)
        real_y = int(y*ratio_y)
        real_w = int(w*ratio_x)
        real_h = int(h*ratio_y)

        blur_value = self.slider_blur.value()
        blur_value = blur_value * 2 + 1
        print(f'Blur slider value: {self.slider_blur.value()}')
        print(f'Blur value: {blur_value}')

        roi = self.img_current[real_y:real_y+real_h, real_x:real_x+real_w]
        blur_slice = cv2.GaussianBlur(roi, (blur_value, blur_value), 0)
        self.img_current[real_y:real_y+real_h, real_x:real_x+real_w] = blur_slice
        self.update_display()


    def update_display(self):
        img_rgb = cv2.cvtColor(self.img_current, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        img = QPixmap.fromImage(q_img)
        img_scaled = img.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lb_image.setPixmap(img_scaled)


    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images ( *.png *.jpg)")
        if file_path:
            print(file_path)
            self.img_bgr = cv2.imread(file_path)
            self.img_current = self.img_bgr.copy()
            self.update_display()


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


    def open_tools1_panel(self):
        self.tool_options.setCurrentWidget(self.grayscale)


    def open_blur_page(self):
        self.tool_options.setCurrentWidget(self.blur)


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