# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loconfig.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox,
    QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu,
    QMenuBar, QPushButton, QRadioButton, QSizePolicy,
    QSpacerItem, QStatusBar, QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(800, 600)
        self.actionWhat_s_This = QAction(MainWindow)
        self.actionWhat_s_This.setObjectName(u"actionWhat_s_This")
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.HelpFaq))
        self.actionWhat_s_This.setIcon(icon)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lo_settings_groupBox = QGroupBox(self.centralwidget)
        self.lo_settings_groupBox.setObjectName(u"lo_settings_groupBox")
        self.formLayout = QFormLayout(self.lo_settings_groupBox)
        self.formLayout.setObjectName(u"formLayout")
        self.tone_list_label = QLabel(self.lo_settings_groupBox)
        self.tone_list_label.setObjectName(u"tone_list_label")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.tone_list_label)

        self.tone_list_horizontalLayout = QHBoxLayout()
        self.tone_list_horizontalLayout.setObjectName(u"tone_list_horizontalLayout")
        self.tone_list_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.tone_list_lineEdit.setObjectName(u"tone_list_lineEdit")

        self.tone_list_horizontalLayout.addWidget(self.tone_list_lineEdit)

        self.tone_list_pushButton = QPushButton(self.lo_settings_groupBox)
        self.tone_list_pushButton.setObjectName(u"tone_list_pushButton")

        self.tone_list_horizontalLayout.addWidget(self.tone_list_pushButton)


        self.formLayout.setLayout(0, QFormLayout.FieldRole, self.tone_list_horizontalLayout)

        self.global_shift_label = QLabel(self.lo_settings_groupBox)
        self.global_shift_label.setObjectName(u"global_shift_label")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.global_shift_label)

        self.global_shift_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.global_shift_lineEdit.setObjectName(u"global_shift_lineEdit")
        self.global_shift_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.global_shift_lineEdit)

        self.df_label = QLabel(self.lo_settings_groupBox)
        self.df_label.setObjectName(u"df_label")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.df_label)

        self.df_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.df_lineEdit.setObjectName(u"df_lineEdit")
        self.df_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.df_lineEdit)

        self.deltaf_label = QLabel(self.lo_settings_groupBox)
        self.deltaf_label.setObjectName(u"deltaf_label")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.deltaf_label)

        self.deltaf_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.deltaf_lineEdit.setObjectName(u"deltaf_lineEdit")
        self.deltaf_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.deltaf_lineEdit)

        self.flagging_label = QLabel(self.lo_settings_groupBox)
        self.flagging_label.setObjectName(u"flagging_label")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.flagging_label)

        self.flagging_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.flagging_lineEdit.setObjectName(u"flagging_lineEdit")
        self.flagging_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.flagging_lineEdit)

        self.filename_suffix_label = QLabel(self.lo_settings_groupBox)
        self.filename_suffix_label.setObjectName(u"filename_suffix_label")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.filename_suffix_label)

        self.show_diagnostics_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.show_diagnostics_checkBox.setObjectName(u"show_diagnostics_checkBox")
        self.show_diagnostics_checkBox.setChecked(True)

        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.show_diagnostics_checkBox)

        self.reveiw_tones_checkbox = QCheckBox(self.lo_settings_groupBox)
        self.reveiw_tones_checkbox.setObjectName(u"reveiw_tones_checkbox")
        self.reveiw_tones_checkbox.setChecked(True)

        self.formLayout.setWidget(7, QFormLayout.LabelRole, self.reveiw_tones_checkbox)

        self.second_sweep_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.second_sweep_checkBox.setObjectName(u"second_sweep_checkBox")
        self.second_sweep_checkBox.setChecked(True)

        self.formLayout.setWidget(9, QFormLayout.LabelRole, self.second_sweep_checkBox)

        self.second_sweep_horizontalLayout = QHBoxLayout()
        self.second_sweep_horizontalLayout.setObjectName(u"second_sweep_horizontalLayout")
        self.second_sweep_df_label = QLabel(self.lo_settings_groupBox)
        self.second_sweep_df_label.setObjectName(u"second_sweep_df_label")
        self.second_sweep_df_label.setEnabled(True)

        self.second_sweep_horizontalLayout.addWidget(self.second_sweep_df_label)

        self.second_sweep_df_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.second_sweep_df_lineEdit.setObjectName(u"second_sweep_df_lineEdit")
        self.second_sweep_df_lineEdit.setEnabled(True)
        self.second_sweep_df_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.second_sweep_horizontalLayout.addWidget(self.second_sweep_df_lineEdit)

        self.second_sweep_horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.second_sweep_horizontalLayout.addItem(self.second_sweep_horizontalSpacer)


        self.formLayout.setLayout(9, QFormLayout.FieldRole, self.second_sweep_horizontalLayout)

        self.filename_suffix_formLayout = QFormLayout()
        self.filename_suffix_formLayout.setObjectName(u"filename_suffix_formLayout")
        self.filename_none_radioButton = QRadioButton(self.lo_settings_groupBox)
        self.buttonGroup = QButtonGroup(MainWindow)
        self.buttonGroup.setObjectName(u"buttonGroup")
        self.buttonGroup.addButton(self.filename_none_radioButton)
        self.filename_none_radioButton.setObjectName(u"filename_none_radioButton")
        self.filename_none_radioButton.setChecked(True)

        self.filename_suffix_formLayout.setWidget(0, QFormLayout.LabelRole, self.filename_none_radioButton)

        self.filename_temperature_radioButton = QRadioButton(self.lo_settings_groupBox)
        self.buttonGroup.addButton(self.filename_temperature_radioButton)
        self.filename_temperature_radioButton.setObjectName(u"filename_temperature_radioButton")
        self.filename_temperature_radioButton.setEnabled(True)
        self.filename_temperature_radioButton.setChecked(False)

        self.filename_suffix_formLayout.setWidget(1, QFormLayout.LabelRole, self.filename_temperature_radioButton)

        self.filename_temperature_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.filename_temperature_lineEdit.setObjectName(u"filename_temperature_lineEdit")
        self.filename_temperature_lineEdit.setEnabled(False)
        self.filename_temperature_lineEdit.setMaximumSize(QSize(200, 16777215))
        self.filename_temperature_lineEdit.setReadOnly(False)

        self.filename_suffix_formLayout.setWidget(1, QFormLayout.FieldRole, self.filename_temperature_lineEdit)

        self.filename_elevation_radioButton = QRadioButton(self.lo_settings_groupBox)
        self.buttonGroup.addButton(self.filename_elevation_radioButton)
        self.filename_elevation_radioButton.setObjectName(u"filename_elevation_radioButton")

        self.filename_suffix_formLayout.setWidget(2, QFormLayout.LabelRole, self.filename_elevation_radioButton)

        self.filename_elevation_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.filename_elevation_lineEdit.setObjectName(u"filename_elevation_lineEdit")
        self.filename_elevation_lineEdit.setEnabled(False)
        self.filename_elevation_lineEdit.setMaximumSize(QSize(200, 16777215))

        self.filename_suffix_formLayout.setWidget(2, QFormLayout.FieldRole, self.filename_elevation_lineEdit)

        self.filename_example_label = QLabel(self.lo_settings_groupBox)
        self.filename_example_label.setObjectName(u"filename_example_label")

        self.filename_suffix_formLayout.setWidget(3, QFormLayout.LabelRole, self.filename_example_label)

        self.filename_example_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.filename_example_lineEdit.setObjectName(u"filename_example_lineEdit")
        self.filename_example_lineEdit.setEnabled(False)
        self.filename_example_lineEdit.setReadOnly(True)

        self.filename_suffix_formLayout.setWidget(3, QFormLayout.FieldRole, self.filename_example_lineEdit)


        self.formLayout.setLayout(5, QFormLayout.FieldRole, self.filename_suffix_formLayout)

        self.only_flag_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.only_flag_checkBox.setObjectName(u"only_flag_checkBox")

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.only_flag_checkBox)


        self.verticalLayout.addWidget(self.lo_settings_groupBox)

        self.dialog_button_box = QDialogButtonBox(self.centralwidget)
        self.dialog_button_box.setObjectName(u"dialog_button_box")
        self.dialog_button_box.setStandardButtons(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)

        self.verticalLayout.addWidget(self.dialog_button_box)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 22))
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName(u"menuFile")
        self.menuHelp = QMenu(self.menubar)
        self.menuHelp.setObjectName(u"menuHelp")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())
        self.menuHelp.addAction(self.actionWhat_s_This)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"LO Sweep Configuration", None))
        self.actionWhat_s_This.setText(QCoreApplication.translate("MainWindow", u"What's This?", None))
#if QT_CONFIG(tooltip)
        self.actionWhat_s_This.setToolTip(QCoreApplication.translate("MainWindow", u"Click on GUI elements for more information", None))
#endif // QT_CONFIG(tooltip)
        self.lo_settings_groupBox.setTitle(QCoreApplication.translate("MainWindow", u"LO Sweep Settings", None))
#if QT_CONFIG(tooltip)
        self.tone_list_label.setToolTip(QCoreApplication.translate("MainWindow", u"Choose a list of resonant frequencies", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.tone_list_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"List of tones of resonant frequencies", None))
#endif // QT_CONFIG(whatsthis)
        self.tone_list_label.setText(QCoreApplication.translate("MainWindow", u"Tone list file:", None))
        self.tone_list_pushButton.setText(QCoreApplication.translate("MainWindow", u"Browse...", None))
#if QT_CONFIG(tooltip)
        self.global_shift_label.setToolTip(QCoreApplication.translate("MainWindow", u"A shift to apply to each tone", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.global_shift_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"Amount to shift each tone in KHz, at 400 MHz", None))
#endif // QT_CONFIG(whatsthis)
        self.global_shift_label.setText(QCoreApplication.translate("MainWindow", u"Global shift at LO frequency (KHz):", None))
        self.global_shift_lineEdit.setText("")
        self.global_shift_lineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"0", None))
#if QT_CONFIG(tooltip)
        self.df_label.setToolTip(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.df_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.df_label.setText(QCoreApplication.translate("MainWindow", u"LO spacing df (KHz):", None))
        self.df_lineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"1", None))
#if QT_CONFIG(tooltip)
        self.deltaf_label.setToolTip(QCoreApplication.translate("MainWindow", u"Total span of sweep in KHZ", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.deltaf_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"Total span of sweep in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.deltaf_label.setText(QCoreApplication.translate("MainWindow", u"Full LO span \u0394f (KHz):", None))
        self.deltaf_lineEdit.setText("")
        self.deltaf_lineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"100", None))
#if QT_CONFIG(tooltip)
        self.flagging_label.setToolTip(QCoreApplication.translate("MainWindow", u"Maximum shift to flag", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.flagging_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"Maximum shift to flag", None))
#endif // QT_CONFIG(whatsthis)
        self.flagging_label.setText(QCoreApplication.translate("MainWindow", u"Maximum shift to flag (KHz):", None))
        self.flagging_lineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"3", None))
#if QT_CONFIG(tooltip)
        self.filename_suffix_label.setToolTip(QCoreApplication.translate("MainWindow", u"Suffix to append to the end of the LO sweep file", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.filename_suffix_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"Suffix to append to the end of the LO sweep file", None))
#endif // QT_CONFIG(whatsthis)
        self.filename_suffix_label.setText(QCoreApplication.translate("MainWindow", u"Filename suffix:", None))
#if QT_CONFIG(tooltip)
        self.show_diagnostics_checkBox.setToolTip(QCoreApplication.translate("MainWindow", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.show_diagnostics_checkBox.setWhatsThis(QCoreApplication.translate("MainWindow", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.show_diagnostics_checkBox.setText(QCoreApplication.translate("MainWindow", u"Show diagnostics", None))
#if QT_CONFIG(tooltip)
        self.reveiw_tones_checkbox.setToolTip(QCoreApplication.translate("MainWindow", u"Review the new tone list after the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.reveiw_tones_checkbox.setWhatsThis(QCoreApplication.translate("MainWindow", u"Review the new tone list after the sweep. Unchecking this box will accept the input tone list", None))
#endif // QT_CONFIG(whatsthis)
        self.reveiw_tones_checkbox.setText(QCoreApplication.translate("MainWindow", u"Review new tones", None))
#if QT_CONFIG(tooltip)
        self.second_sweep_checkBox.setToolTip(QCoreApplication.translate("MainWindow", u"Run a second LO sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.second_sweep_checkBox.setWhatsThis(QCoreApplication.translate("MainWindow", u"Run a second LO sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.second_sweep_checkBox.setText(QCoreApplication.translate("MainWindow", u"Perform second sweep", None))
#if QT_CONFIG(tooltip)
        self.second_sweep_df_label.setToolTip(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.second_sweep_df_label.setWhatsThis(QCoreApplication.translate("MainWindow", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.second_sweep_df_label.setText(QCoreApplication.translate("MainWindow", u"df (KHz):", None))
        self.second_sweep_df_lineEdit.setText(QCoreApplication.translate("MainWindow", u"0.1", None))
        self.filename_none_radioButton.setText(QCoreApplication.translate("MainWindow", u"None", None))
        self.filename_temperature_radioButton.setText(QCoreApplication.translate("MainWindow", u"Focal plane temperature (mK)", None))
        self.filename_elevation_radioButton.setText(QCoreApplication.translate("MainWindow", u"Telescope elevation (deg)", None))
        self.filename_example_label.setText(QCoreApplication.translate("MainWindow", u"Example:", None))
        self.filename_example_lineEdit.setText(QCoreApplication.translate("MainWindow", u"YYYYMMDD_RFSOCX_LO_Sweep_HH", None))
        self.only_flag_checkBox.setText(QCoreApplication.translate("MainWindow", u"Only show flagged resonators", None))
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", u"File", None))
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", u"Help", None))
    # retranslateUi
