#! /usr/bin/env python
"""
wcdma_rrc_analyzer.py

A WCDMA_RRC analyzer
	- Maintain configurations from the SIB
	- Connection setup/release statistics
	- RRCReconfiguration statistics
	- ...

Author: Yuanjie Li
"""

import xml.etree.ElementTree as ET
from analyzer import *
from msg_dump import *
import time
from copy import deepcopy


__all__=["WcdmaRrcAnalyzer"]

class WcdmaRrcAnalyzer(Analyzer):

	def __init__(self):

		Analyzer.__init__(self)

		#init packet filters
		self.add_source_callback(self.__rrc_filter)

		#init internal states
		self.__status=WcdmaRrcStatus()	# current cell status
		self.__history={}	# cell history: timestamp -> WcdmaRrcStatus()
		self.__config={}	# cell_id -> WcdmaRrcConfig()

		#FIXME: change the timestamp
		self.__history[0]=self.__config

		#Temporary structure for holding the config
		#Qualcomm chipset does not report cellID BEFORE SIB, so the update should be delayed
		self.__config_tmp=WcdmaRrcConfig()

	def set_source(self,source):
		Analyzer.set_source(self,source)
		#enable WCDMA RRC log
		source.enable_log("WCDMA_Signaling_Messages")
		source.enable_log("WCDMA_CELL_ID")

	def __rrc_filter(self,msg):
		
		"""
			Filter all RRC packets, and call functions to process it
			
			Args:
				msg: the event (message) from the trace collector
		"""

		log_item = msg.data
		log_item_dict = dict(log_item)

		if msg.type_id=="WCDMA_CELL_ID":
			raw_msg=Event(msg.timestamp,msg.type_id,log_item_dict)
			self.__callback_serv_cell(raw_msg)

		log_xml = None
		if log_item_dict.has_key('Msg'):
			log_xml = ET.fromstring(log_item_dict['Msg'])
		else:
			return

		#Convert msg to xml format
		log_xml = ET.fromstring(log_item_dict['Msg'])
		xml_msg=Event(msg.timestamp,msg.type_id,log_xml)


		if msg.type_id == "WCDMA_Signaling_Messages":	
			self.__callback_sib_config(xml_msg)
			#TODO: callback RRC

		else: #nothing to update
			return

		# Raise event to other analyzers
		# FIXME: the timestamp is incoherent with that from the trace collector
		e = Event(time.time(),self.__class__.__name__,"")
		self.send(e)



	def __callback_serv_cell(self,msg):
		"""
		Update serving cell status
		"""
		if not self.__status.inited():
			#old yet incomplete config would be discarded
			if msg.data.has_key('UTRA DL Absolute RF channel number'):
				self.__status.freq = msg.data['UTRA DL Absolute RF channel number']
			if msg.data.has_key('Cell identity (28-bits)'):
				self.__status.id = msg.data['Cell identity (28-bits)']
			if msg.data.has_key('LAC id'):
				self.__status.lac = msg.data['LAC id']
			if msg.data.has_key('RAC id'):
				self.__status.rac = msg.data['RAC id']

			if self.__status.inited():
				#push the config to the library
				cur_pair=(self.__status.id,self.__status.freq)
				if not self.__config.has_key(cur_pair):
					self.__config[cur_pair] = self.__config_tmp
					self.__config[cur_pair].status = self.__status
				else:
					#FIXME: merge two config? Critical for itner-freq
					for item in self.__config_tmp.sib.inter_freq_config:
						if not self.__config[cur_pair].sib.inter_freq_config.has_key(item):
							self.__config[cur_pair].sib.inter_freq_config[item]\
							=self.__config_tmp.sib.inter_freq_config[item]
		else:
			#if new config arrives, push new one to the history
			if msg.data.has_key('UTRA DL Absolute RF channel number') \
			and self.__status.freq!=msg.data['UTRA DL Absolute RF channel number']:
				print "\033[91m\033[1mNew freq\033[0m\033[0m"
				self.__status=WcdmaRrcStatus()
				self.__status.freq=msg.data['UTRA DL Absolute RF channel number']
				self.__history[msg.timestamp]=self.__status
				#Initialize a new config
				self.__config_tmp=WcdmaRrcConfig()

			if msg.data.has_key('Cell identity (28-bits)') \
			and self.__status.id!=msg.data['Cell identity (28-bits)']:
				print "\033[91m\033[1mNew Cell\033[0m\033[0m"
				self.__status=WcdmaRrcStatus()
				self.__status.id=msg.data['Cell identity (28-bits)']
				self.__history[msg.timestamp]=self.__status
				#Initialize a new config
				self.__config_tmp=WcdmaRrcConfig()
		
			if msg.data.has_key('LAC id') \
			and self.__status.lac!=msg.data['LAC id']:
				self.__status=WcdmaRrcStatus()
				self.__status.lac=msg.data['LAC id']
				self.__history[msg.timestamp]=self.__status
				#Initialize a new config
				self.__config_tmp=WcdmaRrcConfig()
		
			if msg.data.has_key('RAC id') \
			and self.__status.rac!=msg.data['RAC id']:
				self.__status=WcdmaRrcStatus()
				self.__status.rac=msg.data['RAC id']
				self.__history[msg.timestamp]=self.__status
				#Initialize a new config
				self.__config_tmp=WcdmaRrcConfig()



	def __callback_sib_config(self,msg):
		"""
			Callbacks for LTE RRC analysis
		"""
		if self.__status.id==None: #serving cell is not initialized yet
			return

		for field in msg.data.iter('field'):

			#Cell Identity: should be done in __callback_serv_cell
			#But Qualcomm's chipset may report cellID AFTER some configurations
			if field.get('name')=="rrc.cellIdentity":
				cellId = int(field.get('value')[0:-1],16)
				# print "\033[91m\033[1mHahaha\033[0m\033[0m"
				self.__status.dump()
				if not self.__status.inited():
					self.__status.id = cellId
					if self.__status.inited():
						#push the config to the library
						cur_pair = (self.__status.id,self.__status.freq)
						self.__config[cur_pair] = self.__config_tmp
						self.__config[cur_pair].__status = self.__status
				elif self.__status.id != cellId:
					# print "\033[91m\033[1mBug\033[0m\033[0m"
					# print self.__status.id,cellId,self.__status.id.__class__.__name__,cellId.__class__.__name__
					self.__status=WcdmaRrcStatus()
					self.__status.id=cellId
					self.__history[msg.timestamp]=self.__status
					#Initialize a new config
					self.__config_tmp=WcdmaRrcConfig()

			#serving cell info
			if field.get('name')=="rrc.utra_ServingCell_element": 
				field_val={}

				#Default value setting
				#FIXME: set default to those in TS25.331
				field_val['rrc.priority']=None	#mandatory
				field_val['rrc.threshServingLow']=None	#mandatory
				field_val['rrc.s_PrioritySearch1']=None	#mandatory
				field_val['rrc.s_PrioritySearch2']=0	#optional

				for val in field.iter('field'):
					field_val[val.get('name')]=val.get('show')

				
				serv_config = WcdmaRrcSibServ(
					int(field_val['rrc.priority']),
					int(field_val['rrc.threshServingLow'])*2,
					int(field_val['rrc.s_PrioritySearch1'])*2,
					int(field_val['rrc.s_PrioritySearch2']))
				
				if not self.__status.inited():
					self.__config_tmp.sib.serv_config = serv_config
				else:
					cur_pair = (self.__status.id,self.__status.freq)
					self.__config[cur_pair].sib.serv_config = serv_config


			#intra-freq info
			if field.get('name')=="rrc.cellSelectReselectInfo_element":
				field_val={}

				#default value based on TS25.331
				field_val['rrc.s_Intrasearch']=0
				field_val['rrc.s_Intersearch']=0
				field_val['rrc.q_RxlevMin']=None #mandatory
				field_val['rrc.q_QualMin']=None #mandatory
				field_val['rrc.q_Hyst_l_S']=None #mandatory
				field_val['rrc.t_Reselection_S']=None #mandatory
				field_val['rrc.q_HYST_2_S']=None #optional, default=q_Hyst_l_S

				#TODO: handle rrc.RAT_FDD_Info_element (p1530, TS25.331)
				#s-SearchRAT is the RAT-specific threshserv

				#TODO: handle FDD and TDD

				for val in field.iter('field'):
					field_val[val.get('name')]=val.get('show')

				#TS25.331: if qHyst-2s is missing, the default is qHyst-1s
				if field_val['rrc.q_HYST_2_S']==None:
					field_val['rrc.q_HYST_2_S']=field_val['rrc.q_Hyst_l_S']

				intra_freq_config=WcdmaRrcSibIntraFreqConfig(
						int(field_val['rrc.t_Reselection_S']),
						int(field_val['rrc.q_RxlevMin'])*2,
						int(field_val['rrc.s_Intersearch'])*2,
						int(field_val['rrc.s_Intrasearch'])*2,
						int(field_val['rrc.q_Hyst_l_S'])*2,
						int(field_val['rrc.q_HYST_2_S'])*2)

				if not self.__status.inited():		
					self.__config_tmp.sib.intra_freq_config=intra_freq_config
				else:
					cur_pair = (self.__status.id,self.__status.freq)
					self.__config[cur_pair].sib.intra_freq_config=intra_freq_config


			#inter-RAT cell info (LTE)
			if field.get('name')=="rrc.EUTRA_FrequencyAndPriorityInfo_element":
				field_val={}

				print "rrc.EUTRA_FrequencyAndPriorityInfo_element"
				#FIXME: set to the default value based on TS36.331
				field_val['rrc.earfcn']=None
				#field_val['lte-rrc.t_ReselectionEUTRA']=None
				field_val['rrc.priority']=None
				field_val['rrc.qRxLevMinEUTRA']=-140
				#field_val['lte-rrc.p_Max']=None
				field_val['rrc.threshXhigh']=None
				field_val['rrc.threshXlow']=None

				for val in field.iter('field'):
					field_val[val.get('name')]=val.get('show')

				neighbor_freq=int(field_val['rrc.earfcn'])

				inter_freq_config=WcdmaRrcSibInterFreqConfig(
									neighbor_freq,
									#float(field_val['lte-rrc.t_ReselectionEUTRA']),
									None,
									int(field_val['rrc.qRxLevMinEUTRA'])*2,
									#float(field_val['lte-rrc.p_Max']),
									None,
									int(field_val['rrc.priority']),
									int(field_val['rrc.threshXhigh'])*2,
									int(field_val['rrc.threshXlow'])*2
									)
				if not self.__status.inited():
					self.__config_tmp.sib.inter_freq_config[neighbor_freq]=inter_freq_config
				else:
					cur_pair = (self.__status.id,self.__status.freq)
					self.__config[cur_pair].sib.inter_freq_config[neighbor_freq]=inter_freq_config

			#TODO: RRC connection status update

	def get_cell_list(self):
		"""
			Get a complete list of cell IDs *at current location*.
			For these cells, the RrcAnalyzer has the corresponding configurations
			Cells observed yet not camped on would NOT be listed (no config)

			FIXME: currently only return *all* cells in the LteRrcConfig
		"""
		return self.__config.keys()

	def get_cell_config(self,cell):
		"""
			Return a cell's configuration
			cell is a (cell_id,freq) pair
		"""
		if self.__config.has_key(cell):
			return self.__config[cell]
		else:
			return None

	def get_cur_cell(self):
		"""
			Return a cell's configuration
			TODO: if no current cell (inactive), return None
		"""
		return self.__status

	def get_cur_cell_config(self):
		cur_pair=(self.__status.id,self.__status.freq)
		if self.__config.has_key(cur_pair):
			return self.__config[cur_pair]
		else:
			return None



class WcdmaRrcStatus:
	"""
		The metadata of a cell
	"""
	def __init__(self):
		self.id = None #cell ID
		self.freq = None #cell frequency
		self.rat = "UTRA" #radio technology
		self.rac = None #routing area code
		self.lac = None #location area code
		self.bandwidth = None #cell bandwidth
		self.conn = False #connectivity status (for serving cell only)

	def dump(self):
		print self.__class__.__name__,self.id,self.freq,self.rat,self.rac,self.lac

	def inited(self):
		return (self.id!=None and self.freq!=None)

class WcdmaRrcConfig:
	""" 
		Per-cell RRC configurations

		The following configurations should be supported
			- Idle-state
				- Cell reselection parameters
			- Active-state
				- PHY/MAC/PDCP/RLC configuration
				- Measurement configurations
	"""
	def __init__(self):
		self.status = WcdmaRrcStatus() #the metadata of this cell
		self.sib=WcdmaRrcSib()	#Idle-state
		self.active=WcdmaRrcActive() #active-state configurations

	def dump(self):
		print self.__class__.__name__
		self.status.dump()
		self.sib.dump()
		self.active.dump()

	def get_cell_reselection_config(self,cell_meta):

		"""
			Given a cell's metadata, return its reselection config from the serving cell
		"""
		if cell_meta==None:
			return None

		cell = cell_meta.id
		freq = cell_meta.freq

		if freq==self.status.freq: #intra-freq
			hyst = self.sib.intra_freq_config.q_Hyst1
			return WcdmaRrcReselectionConfig(cell,freq,None,hyst,None,None)
		else:
			#inter-frequency/RAT
			#TODO: cell individual offset (not available in AT&T and T-mobile)
			if not self.sib.inter_freq_config.has_key(freq):
				if self.sib.serv_config.priority==None \
				or cell_meta.rat=="UTRA":
					#WCDMA reselection without priority
					hyst = self.sib.intra_freq_config.q_Hyst1
					return WcdmaRrcReselectionConfig(cell,freq,None,hyst,None,None)
			else:
				freq_config = self.sib.inter_freq_config[freq]
				hyst = self.sib.serv_config.s_priority_search2
				return WcdmaRrcReselectionConfig(cell,freq,freq_config.priority, hyst, \
					freq_config.threshx_high,freq_config.threshx_low)

class WcdmaRrcSib:

	"""
		Per-cell Idle-state configurations
	"""
	def __init__(self):
		#FIXME: init based on the default value in TS25.331
		#configuration as a serving cell (LteRrcSibServ)
		self.serv_config = WcdmaRrcSibServ(None,None,None,None) 
		#Intra-freq reselection config
		self.intra_freq_config = WcdmaRrcSibIntraFreqConfig(0,0,None,None,None,None) 
		#Inter-freq/RAT reselection config. Freq/cell -> WcdmaRrcSibInterFreqConfig
		self.inter_freq_config = {}  

	def dump(self):
		self.serv_config.dump()
		self.intra_freq_config.dump()
		for item in self.inter_freq_config:
			self.inter_freq_config[item].dump()

class WcdmaRrcReselectionConfig:
	def __init__(self,cell_id,freq,priority,offset,threshX_High,threshX_Low):
		self.id = cell_id
		self.freq = freq
		self.priority = priority
		self.offset = offset #adjusted offset by considering freq/cell-specific offsets
		self.threshx_high = threshX_High
		self.threshx_low = threshX_Low

class WcdmaRrcSibServ:
	"""
		Serving cell's cell-reselection configurations
	"""
	def __init__(self,priority,thresh_serv, s_priority_search1,s_priority_search2):
		self.priority = priority #cell reselection priority
		self.threshserv_low = thresh_serv #cell reselection threshold
		self.s_priority_search1 = s_priority_search1 #threshold for searching other frequencies
		self.s_priority_search2 = s_priority_search2

	def dump(self):
		print self.__class__.__name__,self.priority,self.threshserv_low,self.s_priority_search1

class WcdmaRrcSibIntraFreqConfig:
	"""
		Intra-frequency cell-reselection configurations
	"""
	def __init__(self,tReselection,q_RxLevMin,s_InterSearch,s_IntraSearch,q_Hyst1,q_Hyst2):
		#FIXME: individual cell offset
		self.tReselection = tReselection
		self.q_RxLevMin = q_RxLevMin
		self.s_InterSearch = s_InterSearch
		self.s_IntraSearch = s_IntraSearch
		self.q_Hyst1 = q_Hyst1
		self.q_Hyst2 = q_Hyst2

	def dump(self):
		print self.__class__.__name__,self.tReselection,self.q_RxLevMin,\
		self.s_InterSearch,self.s_IntraSearch,self.q_Hyst1,self.q_Hyst2

class WcdmaRrcSibInterFreqConfig:
	"""
		Inter-frequency cell-reselection configurations
	"""	
	#FIXME: the current list is incomplete
	#FIXME: individual cell offset
	def __init__(self,freq,tReselection,q_RxLevMin,p_Max,priority,threshx_high,threshx_low):
		self.freq = freq
		self.tReselection = tReselection
		self.q_RxLevMin = q_RxLevMin
		self.p_Max = p_Max
		self.priority = priority
		self.threshx_high = threshx_high
		self.threshx_low = threshx_low

	def dump(self):
		print self.__class__.__name__,self.freq, self.priority, self.tReselection,\
		self.p_Max, self.q_RxLevMin, self.threshx_high, self.threshx_low

class WcdmaRrcActive:
	def __init__(self):
		#TODO: initialize some containers
		pass

	def dump(self):
		pass
