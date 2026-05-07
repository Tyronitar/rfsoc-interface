# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'loconfig.ui'
##
## Created by: Qt User Interface Compiler version 6.11.0
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
        self.scrollArea.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 813, 736))
        self.gridLayout = QGridLayout(self.scrollAreaWidgetContents)
        self.gridLayout.setObjectName(u"gridLayout")
        self.power_sweep_radioButton = QRadioButton(self.scrollAreaWidgetContents)
        self.sweep_type_buttonGroup = QButtonGroup(LoConfigWidget)
        self.sweep_type_buttonGroup.setObjectName(u"sweep_type_buttonGroup")
        self.sweep_type_buttonGroup.addButton(self.power_sweep_radioButton)
        self.power_sweep_radioButton.setObjectName(u"power_sweep_radioButton")

        self.gridLayout.addWidget(self.power_sweep_radioButton, 0, 2, 1, 1)

        self.lo_sweep_radioButton = QRadioButton(self.scrollAreaWidgetContents)
        self.sweep_type_buttonGroup.addButton(self.lo_sweep_radioButton)
        self.lo_sweep_radioButton.setObjectName(u"lo_sweep_radioButton")
        self.lo_sweep_radioButton.setChecked(True)

        self.gridLayout.addWidget(self.lo_sweep_radioButton, 0, 1, 1, 1)

        self.blind_sweep_radioButton = QRadioButton(self.scrollAreaWidgetContents)
        self.sweep_type_buttonGroup.addButton(self.blind_sweep_radioButton)
        self.blind_sweep_radioButton.setObjectName(u"blind_sweep_radioButton")

        self.gridLayout.addWidget(self.blind_sweep_radioButton, 0, 3, 1, 1)

        self.verticalSpacer = QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 4, 1, 1, 1)

        self.sweep_type_label = QLabel(self.scrollAreaWidgetContents)
        self.sweep_type_label.setObjectName(u"sweep_type_label")

        self.gridLayout.addWidget(self.sweep_type_label, 0, 0, 1, 1)

        self.lo_settings_groupBox = QGroupBox(self.scrollAreaWidgetContents)
        self.lo_settings_groupBox.setObjectName(u"lo_settings_groupBox")
        self.lo_gridLayout = QGridLayout(self.lo_settings_groupBox)
        self.lo_gridLayout.setObjectName(u"lo_gridLayout")
        self.channel_label = QLabel(self.lo_settings_groupBox)
        self.channel_label.setObjectName(u"channel_label")

        self.lo_gridLayout.addWidget(self.channel_label, 0, 0, 1, 1)

        self.only_flag_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.only_flag_checkBox.setObjectName(u"only_flag_checkBox")

        self.lo_gridLayout.addWidget(self.only_flag_checkBox, 10, 1, 1, 1)

        self.only_highres_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.only_highres_checkBox.setObjectName(u"only_highres_checkBox")

        self.lo_gridLayout.addWidget(self.only_highres_checkBox, 8, 0, 1, 1)

        self.global_shift_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.global_shift_lineEdit.setObjectName(u"global_shift_lineEdit")
        self.global_shift_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.global_shift_lineEdit, 2, 1, 1, 1)

        self.power_levels_Label = QLabel(self.lo_settings_groupBox)
        self.power_levels_Label.setObjectName(u"power_levels_Label")

        self.lo_gridLayout.addWidget(self.power_levels_Label, 6, 0, 1, 1)

        self.highres_sweep_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.highres_sweep_checkBox.setObjectName(u"highres_sweep_checkBox")
        self.highres_sweep_checkBox.setChecked(True)

        self.lo_gridLayout.addWidget(self.highres_sweep_checkBox, 13, 0, 1, 1)

        self.show_diagnostics_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.show_diagnostics_checkBox.setObjectName(u"show_diagnostics_checkBox")
        self.show_diagnostics_checkBox.setChecked(True)

        self.lo_gridLayout.addWidget(self.show_diagnostics_checkBox, 10, 0, 1, 1)

        self.df_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.df_lineEdit.setObjectName(u"df_lineEdit")
        self.df_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.df_lineEdit, 3, 1, 1, 1)

        self.flagging_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.flagging_lineEdit.setObjectName(u"flagging_lineEdit")
        self.flagging_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.flagging_lineEdit, 5, 1, 1, 1)

        self.deltaf_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.deltaf_lineEdit.setObjectName(u"deltaf_lineEdit")
        self.deltaf_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.lo_gridLayout.addWidget(self.deltaf_lineEdit, 4, 1, 1, 1)

        self.save_plots_CheckBox = QCheckBox(self.lo_settings_groupBox)
        self.save_plots_CheckBox.setObjectName(u"save_plots_CheckBox")
        self.save_plots_CheckBox.setChecked(False)

        self.lo_gridLayout.addWidget(self.save_plots_CheckBox, 10, 2, 1, 1)

        self.df_label = QLabel(self.lo_settings_groupBox)
        self.df_label.setObjectName(u"df_label")

        self.lo_gridLayout.addWidget(self.df_label, 3, 0, 1, 1)

        self.upload_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.upload_checkBox.setObjectName(u"upload_checkBox")

        self.lo_gridLayout.addWidget(self.upload_checkBox, 12, 0, 1, 1)

        self.highres_sweep_save_plots_checkBox = QCheckBox(self.lo_settings_groupBox)
        self.highres_sweep_save_plots_checkBox.setObjectName(u"highres_sweep_save_plots_checkBox")
        self.highres_sweep_save_plots_checkBox.setChecked(False)

        self.lo_gridLayout.addWidget(self.highres_sweep_save_plots_checkBox, 13, 2, 1, 1)

        self.flagging_label = QLabel(self.lo_settings_groupBox)
        self.flagging_label.setObjectName(u"flagging_label")

        self.lo_gridLayout.addWidget(self.flagging_label, 5, 0, 1, 1)

        self.power_levels_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.power_levels_lineEdit.setObjectName(u"power_levels_lineEdit")

        self.lo_gridLayout.addWidget(self.power_levels_lineEdit, 6, 1, 1, 2)

        self.deltaf_label = QLabel(self.lo_settings_groupBox)
        self.deltaf_label.setObjectName(u"deltaf_label")

        self.lo_gridLayout.addWidget(self.deltaf_label, 4, 0, 1, 1)

        self.highres_sweep_horizontalLayout = QHBoxLayout()
        self.highres_sweep_horizontalLayout.setObjectName(u"highres_sweep_horizontalLayout")
        self.highres_sweep_df_label = QLabel(self.lo_settings_groupBox)
        self.highres_sweep_df_label.setObjectName(u"highres_sweep_df_label")
        self.highres_sweep_df_label.setEnabled(True)

        self.highres_sweep_horizontalLayout.addWidget(self.highres_sweep_df_label)

        self.highres_sweep_df_lineEdit = QLineEdit(self.lo_settings_groupBox)
        self.highres_sweep_df_lineEdit.setObjectName(u"highres_sweep_df_lineEdit")
        self.highres_sweep_df_lineEdit.setEnabled(True)
        self.highres_sweep_df_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.highres_sweep_horizontalLayout.addWidget(self.highres_sweep_df_lineEdit)

        self.highres_sweep_horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.highres_sweep_horizontalLayout.addItem(self.highres_sweep_horizontalSpacer)


        self.lo_gridLayout.addLayout(self.highres_sweep_horizontalLayout, 13, 1, 1, 1)

        self.channel_error_label = QLabel(self.lo_settings_groupBox)
        self.channel_error_label.setObjectName(u"channel_error_label")

        self.lo_gridLayout.addWidget(self.channel_error_label, 1, 1, 1, 1)

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

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.filename_none_radioButton)

        self.filename_temperature_radioButton = QRadioButton(self.groupBox)
        self.filename_buttonGroup.addButton(self.filename_temperature_radioButton)
        self.filename_temperature_radioButton.setObjectName(u"filename_temperature_radioButton")
        self.filename_temperature_radioButton.setEnabled(True)
        self.filename_temperature_radioButton.setChecked(False)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.filename_temperature_radioButton)

        self.filename_temperature_lineEdit = QLineEdit(self.groupBox)
        self.filename_temperature_lineEdit.setObjectName(u"filename_temperature_lineEdit")
        self.filename_temperature_lineEdit.setEnabled(False)
        self.filename_temperature_lineEdit.setMaximumSize(QSize(200, 16777215))
        self.filename_temperature_lineEdit.setReadOnly(False)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.filename_temperature_lineEdit)

        self.filename_elevation_radioButton = QRadioButton(self.groupBox)
        self.filename_buttonGroup.addButton(self.filename_elevation_radioButton)
        self.filename_elevation_radioButton.setObjectName(u"filename_elevation_radioButton")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.filename_elevation_radioButton)

        self.filename_elevation_lineEdit = QLineEdit(self.groupBox)
        self.filename_elevation_lineEdit.setObjectName(u"filename_elevation_lineEdit")
        self.filename_elevation_lineEdit.setEnabled(False)
        self.filename_elevation_lineEdit.setMaximumSize(QSize(200, 16777215))

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.filename_elevation_lineEdit)

        self.filename_example_label = QLabel(self.groupBox)
        self.filename_example_label.setObjectName(u"filename_example_label")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.filename_example_label)

        self.filename_example_lineEdit = QLineEdit(self.groupBox)
        self.filename_example_lineEdit.setObjectName(u"filename_example_lineEdit")
        self.filename_example_lineEdit.setEnabled(False)
        self.filename_example_lineEdit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.filename_example_lineEdit.setReadOnly(True)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.filename_example_lineEdit)


        self.lo_gridLayout.addWidget(self.groupBox, 9, 0, 1, 3)

        self.review_tones_checkbox = QCheckBox(self.lo_settings_groupBox)
        self.review_tones_checkbox.setObjectName(u"review_tones_checkbox")
        self.review_tones_checkbox.setChecked(True)

        self.lo_gridLayout.addWidget(self.review_tones_checkbox, 11, 1, 1, 1)

        self.global_shift_label = QLabel(self.lo_settings_groupBox)
        self.global_shift_label.setObjectName(u"global_shift_label")

        self.lo_gridLayout.addWidget(self.global_shift_label, 2, 0, 1, 1)

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

        self.blind_groupBox = QGroupBox(self.lo_settings_groupBox)
        self.blind_groupBox.setObjectName(u"blind_groupBox")
        self.gridLayout_2 = QGridLayout(self.blind_groupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.blind_baseline_lineEdit = QLineEdit(self.blind_groupBox)
        self.blind_baseline_lineEdit.setObjectName(u"blind_baseline_lineEdit")
        self.blind_baseline_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.gridLayout_2.addWidget(self.blind_baseline_lineEdit, 4, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.blind_samples_lineEdit = QLineEdit(self.blind_groupBox)
        self.blind_samples_lineEdit.setObjectName(u"blind_samples_lineEdit")
        self.blind_samples_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.gridLayout_2.addWidget(self.blind_samples_lineEdit, 2, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.blind_noise_fluc_label = QLabel(self.blind_groupBox)
        self.blind_noise_fluc_label.setObjectName(u"blind_noise_fluc_label")

        self.gridLayout_2.addWidget(self.blind_noise_fluc_label, 3, 0, 1, 1)

        self.blind_samples_label = QLabel(self.blind_groupBox)
        self.blind_samples_label.setObjectName(u"blind_samples_label")

        self.gridLayout_2.addWidget(self.blind_samples_label, 2, 0, 1, 1)

        self.blind_res_depth_lineEdit = QLineEdit(self.blind_groupBox)
        self.blind_res_depth_lineEdit.setObjectName(u"blind_res_depth_lineEdit")
        self.blind_res_depth_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.gridLayout_2.addWidget(self.blind_res_depth_lineEdit, 0, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.blind_baseline_label = QLabel(self.blind_groupBox)
        self.blind_baseline_label.setObjectName(u"blind_baseline_label")

        self.gridLayout_2.addWidget(self.blind_baseline_label, 4, 0, 1, 1)

        self.blind_noise_fluc_lineEdit = QLineEdit(self.blind_groupBox)
        self.blind_noise_fluc_lineEdit.setObjectName(u"blind_noise_fluc_lineEdit")
        self.blind_noise_fluc_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.gridLayout_2.addWidget(self.blind_noise_fluc_lineEdit, 3, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.blind_res_depth_label = QLabel(self.blind_groupBox)
        self.blind_res_depth_label.setObjectName(u"blind_res_depth_label")

        self.gridLayout_2.addWidget(self.blind_res_depth_label, 0, 0, 1, 1)

        self.blind_spacing_lineEdit = QLineEdit(self.blind_groupBox)
        self.blind_spacing_lineEdit.setObjectName(u"blind_spacing_lineEdit")
        self.blind_spacing_lineEdit.setMaximumSize(QSize(100, 16777215))

        self.gridLayout_2.addWidget(self.blind_spacing_lineEdit, 1, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.blind_spacing_label = QLabel(self.blind_groupBox)
        self.blind_spacing_label.setObjectName(u"blind_spacing_label")

        self.gridLayout_2.addWidget(self.blind_spacing_label, 1, 0, 1, 1)


        self.lo_gridLayout.addWidget(self.blind_groupBox, 7, 0, 1, 3)


        self.gridLayout.addWidget(self.lo_settings_groupBox, 3, 0, 1, 4)

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
        self.power_levels_Label.setBuddy(self.power_levels_lineEdit)
        self.df_label.setBuddy(self.df_lineEdit)
        self.flagging_label.setBuddy(self.flagging_lineEdit)
        self.deltaf_label.setBuddy(self.deltaf_lineEdit)
        self.highres_sweep_df_label.setBuddy(self.highres_sweep_df_lineEdit)
        self.global_shift_label.setBuddy(self.global_shift_lineEdit)
        self.blind_noise_fluc_label.setBuddy(self.blind_noise_fluc_lineEdit)
        self.blind_samples_label.setBuddy(self.blind_samples_lineEdit)
        self.blind_baseline_label.setBuddy(self.blind_baseline_lineEdit)
        self.blind_res_depth_label.setBuddy(self.blind_res_depth_lineEdit)
        self.blind_spacing_label.setBuddy(self.blind_spacing_lineEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.lo_sweep_radioButton, self.power_sweep_radioButton)
        QWidget.setTabOrder(self.power_sweep_radioButton, self.blind_sweep_radioButton)
        QWidget.setTabOrder(self.blind_sweep_radioButton, self.channel_comboBox)
        QWidget.setTabOrder(self.channel_comboBox, self.channel_toolButton)
        QWidget.setTabOrder(self.channel_toolButton, self.global_shift_lineEdit)
        QWidget.setTabOrder(self.global_shift_lineEdit, self.df_lineEdit)
        QWidget.setTabOrder(self.df_lineEdit, self.deltaf_lineEdit)
        QWidget.setTabOrder(self.deltaf_lineEdit, self.flagging_lineEdit)
        QWidget.setTabOrder(self.flagging_lineEdit, self.power_levels_lineEdit)
        QWidget.setTabOrder(self.power_levels_lineEdit, self.blind_res_depth_lineEdit)
        QWidget.setTabOrder(self.blind_res_depth_lineEdit, self.blind_spacing_lineEdit)
        QWidget.setTabOrder(self.blind_spacing_lineEdit, self.blind_samples_lineEdit)
        QWidget.setTabOrder(self.blind_samples_lineEdit, self.blind_noise_fluc_lineEdit)
        QWidget.setTabOrder(self.blind_noise_fluc_lineEdit, self.blind_baseline_lineEdit)
        QWidget.setTabOrder(self.blind_baseline_lineEdit, self.only_highres_checkBox)
        QWidget.setTabOrder(self.only_highres_checkBox, self.filename_none_radioButton)
        QWidget.setTabOrder(self.filename_none_radioButton, self.filename_temperature_radioButton)
        QWidget.setTabOrder(self.filename_temperature_radioButton, self.filename_temperature_lineEdit)
        QWidget.setTabOrder(self.filename_temperature_lineEdit, self.filename_elevation_radioButton)
        QWidget.setTabOrder(self.filename_elevation_radioButton, self.filename_elevation_lineEdit)
        QWidget.setTabOrder(self.filename_elevation_lineEdit, self.show_diagnostics_checkBox)
        QWidget.setTabOrder(self.show_diagnostics_checkBox, self.only_flag_checkBox)
        QWidget.setTabOrder(self.only_flag_checkBox, self.save_plots_CheckBox)
        QWidget.setTabOrder(self.save_plots_CheckBox, self.review_tones_checkbox)
        QWidget.setTabOrder(self.review_tones_checkbox, self.upload_checkBox)
        QWidget.setTabOrder(self.upload_checkBox, self.highres_sweep_checkBox)
        QWidget.setTabOrder(self.highres_sweep_checkBox, self.highres_sweep_df_lineEdit)
        QWidget.setTabOrder(self.highres_sweep_df_lineEdit, self.highres_sweep_save_plots_checkBox)
        QWidget.setTabOrder(self.highres_sweep_save_plots_checkBox, self.restore_defaults_pushButton)
        QWidget.setTabOrder(self.restore_defaults_pushButton, self.run_pushButton)
        QWidget.setTabOrder(self.run_pushButton, self.filename_example_lineEdit)
        QWidget.setTabOrder(self.filename_example_lineEdit, self.scrollArea)

        self.retranslateUi(LoConfigWidget)

        QMetaObject.connectSlotsByName(LoConfigWidget)
    # setupUi

    def retranslateUi(self, LoConfigWidget):
        LoConfigWidget.setWindowTitle(QCoreApplication.translate("LoConfigWidget", u"LO Sweep Configuration", None))
        self.actionWhat_s_This.setText(QCoreApplication.translate("LoConfigWidget", u"What's This?", None))
#if QT_CONFIG(tooltip)
        self.actionWhat_s_This.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Click on GUI elements for more information", None))
#endif // QT_CONFIG(tooltip)
        self.power_sweep_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Power Sweep", None))
        self.lo_sweep_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"LO Sweep", None))
        self.blind_sweep_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Blind Sweep", None))
        self.sweep_type_label.setText(QCoreApplication.translate("LoConfigWidget", u"Sweep Type:", None))
        self.lo_settings_groupBox.setTitle(QCoreApplication.translate("LoConfigWidget", u"Sweep Settings", None))
        self.channel_label.setText(QCoreApplication.translate("LoConfigWidget", u"Channels:", None))
        self.only_flag_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Only show flagged resonators", None))
        self.only_highres_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Only run high resolution sweep", None))
        self.global_shift_lineEdit.setText("")
        self.global_shift_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"0", None))
        self.power_levels_Label.setText(QCoreApplication.translate("LoConfigWidget", u"Power Levels (dB):", None))
#if QT_CONFIG(tooltip)
        self.highres_sweep_checkBox.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Run a second LO sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.highres_sweep_checkBox.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Run a second LO sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.highres_sweep_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Perform high resolution sweep", None))
#if QT_CONFIG(tooltip)
        self.show_diagnostics_checkBox.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.show_diagnostics_checkBox.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Show diagnostics after running the sweep", None))
#endif // QT_CONFIG(whatsthis)
        self.show_diagnostics_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Show diagnostics", None))
        self.df_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"1", None))
        self.flagging_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"3", None))
        self.deltaf_lineEdit.setText("")
        self.deltaf_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"100", None))
        self.save_plots_CheckBox.setText(QCoreApplication.translate("LoConfigWidget", u"Save resonator plots", None))
#if QT_CONFIG(tooltip)
        self.df_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.df_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.df_label.setText(QCoreApplication.translate("LoConfigWidget", u"LO spacing df (KHz):", None))
        self.upload_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Write new tone list to RFSoC", None))
        self.highres_sweep_save_plots_checkBox.setText(QCoreApplication.translate("LoConfigWidget", u"Save resonator plots", None))
#if QT_CONFIG(tooltip)
        self.flagging_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Maximum shift to flag", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.flagging_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Maximum shift to flag", None))
#endif // QT_CONFIG(whatsthis)
        self.flagging_label.setText(QCoreApplication.translate("LoConfigWidget", u"Maximum shift to flag (KHz):", None))
        self.power_levels_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"-1, 0, 1", None))
#if QT_CONFIG(tooltip)
        self.deltaf_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Total span of sweep in KHZ", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.deltaf_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Total span of sweep in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.deltaf_label.setText(QCoreApplication.translate("LoConfigWidget", u"Full LO span \u0394f (KHz):", None))
#if QT_CONFIG(tooltip)
        self.highres_sweep_df_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.highres_sweep_df_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Spacing between data points in KHz", None))
#endif // QT_CONFIG(whatsthis)
        self.highres_sweep_df_label.setText(QCoreApplication.translate("LoConfigWidget", u"LO Spacing df (KHz):", None))
        self.highres_sweep_df_lineEdit.setText("")
        self.highres_sweep_df_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"0.1", None))
        self.channel_error_label.setText("")
        self.groupBox.setTitle(QCoreApplication.translate("LoConfigWidget", u"Filename Suffix", None))
        self.filename_none_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"None", None))
        self.filename_temperature_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Focal plane temperature (mK)", None))
        self.filename_elevation_radioButton.setText(QCoreApplication.translate("LoConfigWidget", u"Telescope elevation (deg)", None))
        self.filename_example_label.setText(QCoreApplication.translate("LoConfigWidget", u"Example:", None))
        self.filename_example_lineEdit.setText(QCoreApplication.translate("LoConfigWidget", u"YYYYMMDD_rfsocN_LO_Sweep_hourHH", None))
#if QT_CONFIG(tooltip)
        self.review_tones_checkbox.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Review the new tone list after the sweep", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.review_tones_checkbox.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Review the new tone list after the sweep. Unchecking this box will accept the input tone list", None))
#endif // QT_CONFIG(whatsthis)
        self.review_tones_checkbox.setText(QCoreApplication.translate("LoConfigWidget", u"Review new tones", None))
#if QT_CONFIG(tooltip)
        self.global_shift_label.setToolTip(QCoreApplication.translate("LoConfigWidget", u"A shift to apply to each tone", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(whatsthis)
        self.global_shift_label.setWhatsThis(QCoreApplication.translate("LoConfigWidget", u"Amount to shift each tone in KHz, at 400 MHz", None))
#endif // QT_CONFIG(whatsthis)
        self.global_shift_label.setText(QCoreApplication.translate("LoConfigWidget", u"Global shift at LO frequency (KHz):", None))
        self.channel_comboBox.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"Please Select an Item...", None))
#if QT_CONFIG(tooltip)
        self.channel_toolButton.setToolTip(QCoreApplication.translate("LoConfigWidget", u"Open in \"Initialization\" tab", None))
#endif // QT_CONFIG(tooltip)
        self.channel_toolButton.setText(QCoreApplication.translate("LoConfigWidget", u"...", None))
        self.blind_groupBox.setTitle(QCoreApplication.translate("LoConfigWidget", u"Blind Sweep Resonance Finding Parameters", None))
        self.blind_baseline_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"50", None))
        self.blind_samples_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"2", None))
        self.blind_noise_fluc_label.setText(QCoreApplication.translate("LoConfigWidget", u"Maximum Noise Fluctuation (dB):", None))
        self.blind_samples_label.setText(QCoreApplication.translate("LoConfigWidget", u"Minimum Samples per Resonance:", None))
        self.blind_res_depth_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"0.2", None))
        self.blind_baseline_label.setText(QCoreApplication.translate("LoConfigWidget", u"Baseline Percentile:", None))
        self.blind_noise_fluc_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"0.05", None))
        self.blind_res_depth_label.setText(QCoreApplication.translate("LoConfigWidget", u"Min Resonance Depth (dB):", None))
        self.blind_spacing_lineEdit.setPlaceholderText(QCoreApplication.translate("LoConfigWidget", u"3000", None))
        self.blind_spacing_label.setText(QCoreApplication.translate("LoConfigWidget", u"Minimum Space Between Resonances (Hz):", None))
        self.restore_defaults_pushButton.setText(QCoreApplication.translate("LoConfigWidget", u"Restore Defaults", None))
        self.run_pushButton.setText(QCoreApplication.translate("LoConfigWidget", u"Run Sweep", None))
    # retranslateUi

