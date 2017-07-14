#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
from os.path import dirname

import logging

from loopchain.blockchain import ScoreBase
from loopchain.tools import ScoreDatabaseType, ScoreHelper


class UserScore(ScoreBase):
    CONTRACT_DB_ID = 'contract'
    USER_DB_ID = 'user'
    LOG_PREFIX = "[CONTRACT SAMPLE SCORE] "
    DB_ENCODING = "UTF-8"
    # for find last index
    LAST_INDEX_KEY = "last_index"

    # json keys
    PROPOSER = "proposer"
    COUNTERPARTIES = "counterparties"
    CONTENT = "content"
    QUORUM = "quorum"
    APPROVERS = "approvers"
    USER_ID  = "user_id"
    CONTRACT_ID = "contract_id"

    def __init__(self, info=None):
        """체인코드 생성
        체인코드 디비 생성
        """
        super().__init__(info)
        if info is None:
            with open(dirname(__file__)+'/'+ScoreBase.PACKAGE_FILE, "r") as f:
                self.__score_info = json.loads(f.read())
                f.close()
        else:
            self.__score_info = info
        self.__contract_db = None
        self.__user_db = None

    def __init_db(self):
        helper = ScoreHelper()
        if self.__contract_db is None:
            logging.debug(self.LOG_PREFIX + "Init DB(%s)", self.CONTRACT_DB_ID)
            self.__contract_db = helper.load_database(score_id=self.CONTRACT_DB_ID, database_type=ScoreDatabaseType.leveldb)
        if self.__user_db is None:
            logging.debug(self.LOG_PREFIX + "Init DB(%s)", self.USER_DB_ID)
            self.__user_db = helper.load_database(score_id=self.USER_DB_ID, database_type=ScoreDatabaseType.leveldb)

    # Invoke Sub-main
    def invoke(self, transaction, block):
        """transaction 실행
        :param transaction:
        :param block:
        :return:
        """
        self.__init_db()
        data = transaction.get_data_string()
        tx_data = json.loads(data)
        logging.debug(self.LOG_PREFIX + "tx_data : %s", tx_data)

        tx_method = tx_data['method']
        logging.debug(self.LOG_PREFIX + 'find')

        if tx_method == "propose":
            logging.debug(self.LOG_PREFIX + 'propose start')
            self.propose(tx_data['params'])
        elif tx_method == "approve":
            self.approve(tx_data['params'])
        else:
            logging.error(self.LOG_PREFIX + "Unknown transaction method : " + tx_method)
            raise Exception('method not found')

    def query(self, query_request):
        """인증서 생성 및 인증서 검증
        :param query_request:
        :return:
        """
        self.__init_db()
        try:
            req = json.loads(query_request)
            q_method = req["method"]
            q_id = req['id']

            # DN 요청
            if q_method == 'get_user_contracts':
                user_contracts = self.get_user_contracts(req['params'])
                if user_contracts is not None:
                    response = {"jsonrpc": "2.0", "code": 0, "response": {"user_contracts": user_contracts}, "id": q_id}
                else:
                    response = {"jsonrpc": "2.0", "code": -1, "response": {}, "id": q_id}

                return json.dumps(response)
        except Exception as e:
            logging.error("query error" + e )

    def info(self):
        pass

    def propose(self, params):
        """ add new contract  메세지 검사 생략

        :param params: {"proposer": , "counterparties": [counterparties], "content": "contract text", "quorum": "(int)quorum"}
        :return:
        """
        logging.debug(self.LOG_PREFIX + 'propose -2')

        params[self.APPROVERS] = [params[self.PROPOSER]]
        logging.debug(self.LOG_PREFIX + 'propose -1')

        new_index = self.__get_last_index() + 1
        logging.debug(self.LOG_PREFIX + 'propose 0')

        input_contract = self.__json_to_utf8_str(params)
        logging.debug(self.LOG_PREFIX + 'propose 1')

        self.__contract_db.Put(new_index, input_contract)
        logging.debug(self.LOG_PREFIX + 'propose 2')

        self.__contract_db.Put(self.LAST_INDEX_KEY, new_index)
        logging.debug(self.LOG_PREFIX + 'propose 3')


        for counterpart in params[self.COUNTERPARTIES]:
            counterpart_contracts = self.__user_db.Get(counterpart)
            logging.debug(self.LOG_PREFIX + 'propose 4')

            if counterpart_contracts is None:
                counterpart_contracts = "[]"

            contract_list = json.loads(counterpart_contracts)
            logging.debug(self.LOG_PREFIX + 'propose 5')

            contract_list.append(new_index)
            logging.debug(self.LOG_PREFIX + 'propose 6')

            input_contract_list = self.__json_to_utf8_str(contract_list)
            logging.debug(self.LOG_PREFIX + 'propose 7')

            self.__user_db.Put(counterpart, input_contract_list)
            logging.debug(self.LOG_PREFIX + 'propose 8')

        return {'code': 0}

    def __json_to_utf8_str(self, json_data):
        json_str = json.dumps(json_data)
        logging.debug(self.LOG_PREFIX + '__json_to_utf8_str 1')

        return json_str.encode(self.DB_ENCODING)

    def __get_last_index(self):
        last_index = self.__contract_db.Get(self.LAST_INDEX_KEY)
        if last_index is None:
            last_index = 0
            self.__contract_db.Put(self.LAST_INDEX_KEY, last_index)
        return last_index

    def approve(self, params):
        """ approve one contract

        :param params: user_id, contract_id in json_params
        :return:
        """
        contract_id = params[self.CONTRACT_ID]
        approve_user = params[self.USER_ID]
        logging.debug(self.LOG_PREFIX + 'approve 1')

        contract_str = self.__contract_db.Get(contract_id)
        logging.debug(self.LOG_PREFIX + 'approve 2')

        contract = json.loads(contract_str, encoding=self.DB_ENCODING)
        logging.debug(self.LOG_PREFIX + 'approve 3')


        if approve_user in contract[self.COUNTERPARTIES]:

            if approve_user not in contract[self.APPROVERS]:
                contract[self.APPROVERS].append(approve_user)
                logging.debug(self.LOG_PREFIX + 'approve 4')

                input_contract = self.__json_to_utf8_str(contract)
                logging.debug(self.LOG_PREFIX + 'approve 5')

                self.__contract_db.Put(contract_id, input_contract)
                logging.debug(self.LOG_PREFIX + 'approve 6')

                return {'code': 0}
            else:
                raise Exception('previous approve user' + approve_user)
        else:
            raise Exception('this user is not in counterparties')

    def get_user_contracts(self, params):
        """ get user contracts

        :param params: user_id in json_params
        :return:
        """
        user_id = params[self.USER_ID]
        logging.debug(self.LOG_PREFIX + 'get_user_contracts 1')

        contract_id_str = self.__user_db.Get(user_id)
        logging.debug(self.LOG_PREFIX + 'get_user_contracts 2')

        contract_id_list = json.loads(contract_id_str, encoding=self.DB_ENCODING)
        logging.debug(self.LOG_PREFIX + 'get_user_contracts 3')


        contract_list = []
        # get all user contracts
        for contract_id in contract_id_list:
            contract = self.__contract_db.Get(contract_id)
            logging.debug(self.LOG_PREFIX + 'get_user_contracts 4')

            contract_json = json.loads(contract, encoding=self.DB_ENCODING)
            logging.debug(self.LOG_PREFIX + 'get_user_contracts 5')

            # add id to response
            contract_json[self.CONTRACT_ID] = contract_id
            logging.debug(self.LOG_PREFIX + 'get_user_contracts 6')

            contract_list.append(contract_json)
            logging.debug(self.LOG_PREFIX + 'get_user_contracts 7')

        return contract_list




