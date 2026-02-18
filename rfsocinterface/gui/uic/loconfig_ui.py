# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loconfig.ui'
##
## Created by: Qt User Interface Compiler version 6.8.1
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
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSpacerItem, QToolButton, QVBoxLayout,
    QWidget)

from rfsocinterface.gui.widgets.combo_box import CheckableComboBox
from . import icons_rc

class Ui_LoConfigWidget(object):
    def setupUi(self, LoConfigWidget):
        if not LoConfigWidget.objectName():
            LoConfigWidget.setObjectName(u"LoConfigWidget")
        LoConfigWidget.resize(847, 758)
        self.actionWhat_s_This = QAction(LoConfigWidget)
        self.actionWhat_s_This.setObjectName(u"actionWhat_s_This")
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.HelpFaq))
        self.actionWhat_s_This.setIcon(icon)
        self.verticalLayout_2 = QVBoxLayout(LoConfigWidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.scrollArea = QScrollArea(LoConfigWidget)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 827, 705))
        self.verticalLayout_3 = QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.lo_sweep_radioButton = QRadioButton(self.scrollAreaWidgetContents)
        self.sweep_type_buttonGroup = QButtonGroup(LoConfigWidget)
        self.sweep_type_buttonGroup.setObjectName(u"sweep_type_buttonGroup")
        self.sweep_type_buttonGroup.addButton(self.lo_sweep_radioButton)
        self.lo_sweep_radioButton.setObjectName(u"lo_sweep_radioButton")
        self.lo_sweep_radioButton.setChecked(True)

        self.verticalLayout_3.addWidget(self.lo_sweep_radioButton)

        self.power_sweep_radioButton = QRadioButton(self.scrollAreaWidgetContents)
        self.sweep_type_buttonGroup.addButton(self.power_sweep_radioButton)
        self.power_sweep_radioButton.setObjectName(u"power_sweep_radioButton")

        self.verticalLayout_3.addWidget(self.power_sweep_radioButton)

        self.blind_sweep_radioButton = QRadioButton(self.scrollAreaWidgetContents)
        self.sweep_type_buttonGroup.addButton(self.blind_sweep_radioButton)
        self.blind_sweep_radioButton.setObjectName(u"blind_sweep_radioButton")

        self.verticalLayout_3.addWidget(self.blind_sweep_radioButton)

        self.lo_settings_groupBox = QGroupBox(self.scrollAreaWidgetContents)
        self.lo_settings_groupBox.setObjectName(u"lo_settings_groupBox")
        self.lo_gridLayout = QGridLayout(self.lo_settings_groupBox)
        self.lo_gridLayout.setObjectName(u"lo_gridLayout")
        self.channel_error_label = QLabel(self.lo_settings_groupBox)
        self.channel_error_label.setObjectName(u"channel_error_label")

        self.lo_gridLayout.addWidget(self.channel_error_label, 1, 1, 1, 1)

        self.df_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.df_lineEdit.setObjectName(u"df_lineEdit")
        self.df_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.df_lineEdit, 3, 1, 1, 1)

        self.deltaf_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.deltaf_lineEdit.setObjectName(u"deltaf_lineEdit")
        self.deltaf_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.deltaf_lineEdit, 4, 1, 1, 1)

        self.global_shift_label = QLabel(self.lo_settings_groupBox)
        self.global_shift_label.setObjectName(u"global_shift_label")

        self.lo_gridLayout.addWidget(self.global_shift_label, 2, 0, 1, 1)

        self.flagging_label = QLabel(self.lo_settings_groupBox)
        self.flagging_label.setObjectName(u"flagging_label")

        self.lo_gridLayout.addWidget(self.flagging_label, 5, 0, 1, 1)

        self.upload_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.upload_checkBox.setObjectName(u"upload_checkBox")

        self.lo_gridLayout.addWidget(self.upload_checkBox, 10, 0, 1, 1)

        self.groupBox = QGroupBox(self.lo_settings_groupBox)
        self.groupBox.setObjectName(u"groupBox")
        self.formLayout = QFormLayout(self.groupBox)
        self.formLayout.setObjectName(u"formLayout")
        self.filename_none_radioButton = QRadioButton(self.groupBox)
        self.filename_buttonGroup = QButtonGroup(LoConfigWidget)
        self.filename_buttonGroup.setObjectName(u"filename_buttonGroup")
        self.filename_buttonGroup.addButton(self.filename_none_radioButton)
        self.filename_none_radioButton.setObjectName(u"filename_none_radioButton")
        self.filename_none_radioButton.setChecked(True)

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.filename_none_radioButton)

        self.filename_temperature_radioButton = QRadioButton(self.groupBox)
        self.filename_buttonGroup.addButton(self.filename_temperature_radioButton)
        self.filename_temperature_radioButton.setObjectName(u"filename_temperature_radioButton")
        self.filename_temperature_radioButton.setEnabled(True)
        self.filename_temperature_radioButton.setChecked(False)

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.filename_temperature_radioButton)

        self.filename_temperature_lineEdit = QLineEdit(self.groupBox)
        self.filename_temperature_lineEdit.setObjectName(u"filename_temperature_lineEdit")
        self.filename_temperature_lineEdit.setEnabled(False)
        self.filename_temperature_lineEdit.setMaximumSize(QSize(200, 16777215))
        self.filename_temperature_lineEdit.setReadOnly(False)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.filename_temperature_lineEdit)

        self.filename_elevation_radioButton = QRadioButton(self.groupBox)
        self.filename_buttonGroup.addButton(self.filename_elevation_radioButton)
        self.filename_elevation_radioButton.setObjectName(u"filename_elevation_radioButton")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.filename_elevation_radioButton)

        self.filename_elevation_lineEdit = QLineEdit(self.groupBox)
        self.filename_elevation_lineEdit.setObjectName(u"filename_elevation_lineEdit")
        self.filename_elevation_lineEdit.setEnabled(False)
        self.filename_elevation_lineEdit.setMaximumSize(QSize(200, 16777215))

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.filename_elevation_lineEdit)

        self.filename_example_label = QLabel(self.groupBox)
        self.filename_example_label.setObjectName(u"filename_example_label")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.filename_example_label)

        self.filename_example_lineEdit = QLineEdit(self.groupBox)
        self.filename_example_lineEdit.setObjectName(u"filename_example_lineEdit")
        self.filename_example_lineEdit.setEnabled(False)
        self.filename_example_lineEdit.setReadOnly(True)

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.filename_example_lineEdit)


        self.lo_gridLayout.addWidget(self.groupBox, 7, 0, 1, 3)

        self.channel_label = QLabel(self.lo_settings_groupBox)
        self.channel_label.setObjectName(u"channel_label")

        self.lo_gridLayout.addWidget(self.channel_label, 0, 0, 1, 1)

        self.review_tones_checkbox = QCheckBox(self.lo_settings_groupBox)
        self.review_tones_checkbox.setObjectName(u"review_tones_checkbox")
        self.review_tones_checkbox.setChecked(True)

        self.lo_gridLayout.addWidget(self.review_tones_checkbox, 9, 1, 1, 1)

        self.only_flag_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.only_flag_checkBox.setObjectName(u"only_flag_checkBox")

        self.lo_gridLayout.addWidget(self.only_flag_checkBox, 8, 1, 1, 1)

        self.second_sweep_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.second_sweep_checkBox.setObjectName(u"second_sweep_checkBox")
        self.second_sweep_checkBox.setChecked(True)

        self.lo_gridLayout.addWidget(self.second_sweep_checkBox, 11, 0, 1, 1)

        self.df_label = QLabel(self.lo_settings_groupBox)
        self.df_label.setObjectName(u"df_label")

        self.lo_gridLayout.addWidget(self.df_label, 3, 0, 1, 1)

        self.save_plots_CheckBox = QCheckBox(self.lo_settings_groupBox)
        self.save_plots_CheckBox.setObjectName(u"save_plots_CheckBox")
        self.save_plots_CheckBox.setChecked(False)

        self.lo_gridLayout.addWidget(self.save_plots_CheckBox, 8, 2, 1, 1)

        self.deltaf_label = QLabel(self.lo_settings_groupBox)
        self.deltaf_label.setObjectName(u"deltaf_label")

        self.lo_gridLayout.addWidget(self.deltaf_label, 4, 0, 1, 1)

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


        self.lo_gridLayout.addLayout(self.second_sweep_horizontalLayout, 11, 1, 1, 1)

        self.second_sweep_save_plots_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.second_sweep_save_plots_checkBox.setObjectName(u"second_sweep_save_plots_checkBox")
        self.second_sweep_save_plots_checkBox.setChecked(False)

        self.lo_gridLayout.addWidget(self.second_sweep_save_plots_checkBox, 11, 2, 1, 1)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.channel_comboBox = CheckableComboBox(self.lo_settings_groupBox)
        self.channel_comboBox.setObjectName(u"channel_comboBox")

        self.horizontalLayout.addWidget(self.channel_comboBox)

        self.channel_toolButton = QToolButton(self.lo_settings_groupBox)
        self.channel_toolButton.setObjectName(u"channel_toolButton")
        icon1 = QIcon()
        icon1.addFile(u":/icons/external-link.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.channel_toolButton.setIcon(icon1)

        self.horizontalLayout.addWidget(self.channel_toolButton)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)


        self.lo_gridLayout.addLayout(self.horizontalLayout, 0, 1, 1, 1)

        self.global_shift_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.global_shift_lineEdit.setObjectName(u"global_shift_lineEdit")
        self.global_shift_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.global_shift_lineEdit, 2, 1, 1, 1)

        self.show_diagnostics_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.show_diagnostics_checkBox.setObjectName(u"show_diagnostics_checkBox")
        self.show_diagnostics_checkBox.setChecked(True)

        self.lo_gridLayout.addWidget(self.show_diagnostics_checkBox, 8, 0, 1, 1)

        self.flagging_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.flagging_lineEdit.setObjectName(u"flagging_lineEdit")
        self.flagging_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.flagging_lineEdit, 5, 1, 1, 1)

        self.power_levels_Label = QLabel(self.lo_settings_groupBox)
        self.power_levels_Label.setObjectName(u"power_levels_Label")

        self.lo_gridLayout.addWidget(self.power_levels_Label, 6, 0, 1, 1)

        self.power_levels_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.power_levels_lineEdit.setObjectName(u"power_levels_lineEdit")

        self.lo_gridLayout.addWidget(self.power_levels_lineEdit, 6, 1, 1, 1)


        self.verticalLayout_3.addWidget(self.lo_settings_groupBox)

        self.verticalSpacer = QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_3.addItem(self.verticalSpacer)

        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.verticalLayout_2.addWidget(self.scrollArea)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.restore_defaults_pushButton = QPushButton(LoConfigWidget)
        self.restore_defaults_pushButton.setObjectName(u"restore_defaults_pushButton")

        self.horizontalLayout_2.addWidget(self.restore_defaults_pushButton)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_2)

        self.run_pushButton = QPushButton(LoConfigWidget)
        self.run_pushButton.setObjectName(u"run_pushButton")

        self.horizontalLayout_2.addWidget(self.run_pushButton)


        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

#if QT_CONFIG(shortcut)
        self.global_shift_label.setBuddy(self.global_shift_lineEdit)
        self.flagging_label.setBuddy(self.flagging_lineEdit)
        self.df_label.setBuddy(self.df_lineEdit)
        self.deltaf_label.setBuddy(self.deltaf_lineEdit)
        self.second_sweep_df_label.setBuddy(self.second_sweep_df_lineEdit)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(LoConfigWidget)

        QMetaObject.connectSlotsByName(LoConfigWidget)
    # setupUi

    def retranslateUi(self, LoConfigWidget):
        LoConfigWidget.setWindowTitle(QCoreApplication.translate("LoConfigWidget", u"LO Sweep Configuration", None))
        self.actionWhat_s_This.setText(QCoreApplication.translate("LoConfigWidget", u"What's This?", None))
#if QT_CONFIG(tooltip)
        self.actionWhat_s_This.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Click on GUI elements for more information", None))
#endif // QT_CONFIG(tooltip)
        self.lo_sweep_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"LO Sweep", None))
        self.power_sweep_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Power Sweep", None))
        self.blind_sweep_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Blind Sweep", None))
        self.lo_settings_groupBox.setTitle(QCoreApplication.translate("LoConfigWidget", u"Sweep Settings", None))
        self.channel_error_label.setText("")
        self.df_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"1", None))
        self.deltaf_lineEdit.setText("")
        self.deltaf_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"100", None))
#if QT_CONFIG(tooltip)
        self.global_shift_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"A shift to apply to each tone", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.global_shift_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Amount to shift each tone in KHz, at 400 MHz", None))
#endif // QT_CONFIG(whatsthis)
        self.global_shift_label.setText(QCoreApplication.translate("LoConfigWidget", u"Global shift at LO frequency (KHz):", None))
#if QT_CONFIG(tooltip)
        self.flagging_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Maximum shift to flag", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.flagging_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Maximum shift to flag", None))
#endif // QT_CONFIG(whatsthis)
        self.flagging_label.setText(QCoreApplication.translate("LoConfigWidget", u"Maximum shift to flag (KHz):", None))
        self.upload_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Write new tone list to RFSoC", None))
        self.groupBox.setTitle(QCoreApplication.translate("LoConfigWidget", u"Filename Suffix", None))
        self.filename_none_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"None", None))
        self.filename_temperature_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Focal plane temperature (mK)", None))
        self.filename_elevation_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Telescope elevation (deg)", None))
        self.filename_example_label.setText(QCoreApplication.translate("LoConfigWidget", u"Example:", None))
        self.filename_example_lineEdit.setText(QCoreApplication.translate("LoConfigWidget", u"YYYYMMDD_rfsocN_LO_Sweep_hourHH", None))
        self.channel_label.setText(QCoreApplication.translate("LoConfigWidget", u"Channels:", None))
#if QT_CONFIG(tooltip)
        self.review_tones_checkbox.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Review the new tone list after the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.review_tones_checkbox.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Review the new tone list after the sweep. Unchecking this box will accept the input tone list", None))
#endif // QT_CONFIG(whatsthis)
        self.review_tones_checkbox.setText(QCoreApplication.translate("LoConfigWidget", u"Review new tones", None))
        self.only_flag_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Only show flagged resonators", None))
#if QT_CONFIG(tooltip)
        self.second_sweep_checkBox.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Run a second LO sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.second_sweep_checkBox.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Run a second LO sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.second_sweep_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Perform second sweep", None))
#if QT_CONFIG(tooltip)
        self.df_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.df_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.df_label.setText(QCoreApplication.translate("LoConfigWidget", u"LO spacing df (KHz):", None))
        self.save_plots_CheckBox.setText(QCoreApplication.translate("LoConfigWidget", u"Save resonator plots", None))
#if QT_CONFIG(tooltip)
        self.deltaf_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Total span of sweep in KHZ", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.deltaf_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Total span of sweep in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.deltaf_label.setText(QCoreApplication.translate("LoConfigWidget", u"Full LO span \u0394f (KHz):", None))
#if QT_CONFIG(tooltip)
        self.second_sweep_df_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.second_sweep_df_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.second_sweep_df_label.setText(QCoreApplication.translate("LoConfigWidget", u"LO Spacing df (KHz):", None))
        self.second_sweep_df_lineEdit.setText("")
        self.second_sweep_df_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"0.1", None))
        self.second_sweep_save_plots_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Save resonator plots", None))
        self.channel_comboBox.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"Please Select an Item...", None))
#if QT_CONFIG(tooltip)
        self.channel_toolButton.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Open in \"Initialization\" tab", None))
#endif // QT_CONFIG(tooltip)
        self.channel_toolButton.setText(QCoreApplication.translate("LoConfigWidget", u"...", None))
        self.global_shift_lineEdit.setText("")
        self.global_shift_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"0", None))
#if QT_CONFIG(tooltip)
        self.show_diagnostics_checkBox.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.show_diagnostics_checkBox.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.show_diagnostics_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Show diagnostics", None))
        self.flagging_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"3", None))
        self.power_levels_Label.setText(QCoreApplication.translate("LoConfigWidget", u"Power Levels (dB):", None))
        self.restore_defaults_pushButton.setText(QCoreApplication.translate("LoConfigWidget", u"Restore Defaults", None))
        self.run_pushButton.setText(QCoreApplication.translate("LoConfigWidget", u"Run Sweep", None))
    # retranslateUi

