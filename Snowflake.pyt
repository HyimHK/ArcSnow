# -*- coding: utf-8 -*-

import os
import sys

from cryptography.fernet import Fernet
import ctypes
import arcpy
import csv
import pandas as pd
import snowflake.connector


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Snowflake ETL"
        self.alias = "snowflake_toolbox"

        # List of tool classes associated with this toolbox
        self.tools = [test_credentials, cvs_upload, drop_table, download_table, generate_credentials]

class test_credentials(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Test Credentials"
        self.description = "Test a Snowflake credential"
        self.canRunInBackground = False
        self.category = "Preparation"
        
    def getParameterInfo(self):
        """Define parameter definitions"""
        credentials = arcpy.Parameter(
            displayName="Credentials File",
            name="credentials",
            datatype="DEFile",
            parameterType="Required",
            direction="Input")
        
        valid = arcpy.Parameter(
            displayName="Is Valid",
            name="valid",
            datatype="GPBoolean",
            parameterType="Derived",
            direction="Output")
        
        return [credentials, valid]
        
    def execute(self, parameters, messages):
        parameters[1].value = False
        
        arcsnow = ArcSnow(parameters[0].valueAsText)
        arcsnow.login()
        
        parameters[1].value = True
        
        
class generate_credentials(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Generate Credential File"
        self.description = "Create a credentials file used to authenticate with Snowflake"
        self.canRunInBackground = False
        self.category = "Preparation"
        
    def getParameterInfo(self):
        """Define parameter definitions"""
        username = arcpy.Parameter(
            displayName="Username",
            name="username",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
            
        password = arcpy.Parameter(
            displayName="Password",
            name="password",
            datatype="GPStringHidden",
            parameterType="Required",
            direction="Input")
            
        account = arcpy.Parameter(
            displayName="Account",
            name="account",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
            
        warehouse = arcpy.Parameter(
            displayName="Warehouse",
            name="warehouse",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
            
        database = arcpy.Parameter(
            displayName="Database",
            name="database",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
            
        schema = arcpy.Parameter(
            displayName="Schema",
            name="schema",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        output_path = arcpy.Parameter(
            displayName="Output Location",
            name="output",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
            
        out_file = arcpy.Parameter(
            displayName = "Out Credential File",
            name = "credential_filepath",
            datatype = "DEFile",
            parameterType = "Derived",
            direction = "Output")
         
        output_path.value = arcpy.mp.ArcGISProject("CURRENT").homeFolder

        return [username, password, account, warehouse, database, schema, output_path, out_file]

    def updateParameters(self, parameters):
        if not parameters[6].value:
            parameters[6].value = arcpy.mp.ArcGISProject("CURRENT").homeFolder
                      
        if not parameters[6].hasBeenValidated or not parameters[6].altered:
            credentials = Credentials()
            credentials.location = parameters[6].valueAsText
            parameters[7].value = credentials.path
        
    def execute(self, parameters, messages):        
        credentials = Credentials()
        
        credentials.username = parameters[0].valueAsText
        credentials.password = parameters[1].valueAsText
        credentials.account = parameters[2].valueAsText
        credentials.warehouse = parameters[3].valueAsText
        credentials.database = parameters[4].valueAsText
        credentials.schema = parameters[5].valueAsText
        credentials.location = parameters[6].valueAsText
        
        credentials.create_cred()
        
        parameters[7].value = credentials.path
        

class download_table(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Download Table"
        self.description = "Convert a Snowflake table to a GDB table"
        self.canRunInBackground = False
        self.category = "ETL"

    def getParameterInfo(self):
        """Define parameter definitions"""
                   
        credentials = arcpy.Parameter(
            displayName="Credentials File",
            name="credentials",
            datatype="DEFile",
            parameterType="Required",
            direction="Input")
        
        table_name = arcpy.Parameter(
            displayName="Table Name",
            name="table_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        out_database = arcpy.Parameter(
            displayName="Target Database",
            name="out_database",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        out_database.value = arcpy.env.workspace

        out_name = arcpy.Parameter(
            displayName="Output Name",
            name="out_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        limit = arcpy.Parameter(
            displayName="Limit",
            name="limit",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")

        row_count = arcpy.Parameter(
            displayName="Row Count",
            name="row_count",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        
        return [credentials, table_name, out_database, out_name, limit, row_count]
    
    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated and parameters[0].valueAsText:
            arcsnow = ArcSnow(parameters[0].valueAsText)
            arcsnow.login()

            parameters[1].filter.type = "ValueList"       
            parameters[1].filter.list = [row[0] for row in arcsnow.cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES \
            WHERE TABLE_SCHEMA NOT LIKE 'INFORMATION_SCHEMA'")]
            
            arcsnow.logout()
        
        
        if not parameters[1].hasBeenValidated and parameters[1].valueAsText:
            parameters[3].value = os.path.splitext(os.path.basename(parameters[1].valueAsText))[0]

        return

    def execute(self, parameters, messages):
        table_name = parameters[1].valueAsText
        out_database = parameters[2].valueAsText
        out_name = parameters[3].valueAsText
        limit = parameters[4].value
        row_count = parameters[5].value

        arcsnow = ArcSnow(parameters[0].valueAsText)
        arcsnow.login()

        columns = arcsnow.cursor.execute(f"""SELECT COLUMN_NAME, IS_NULLABLE, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, DATETIME_PRECISION FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{table_name}' ORDER BY ORDINAL_POSITION""")

        fc = arcpy.management.CreateTable(out_database, out_name)
        for field in columns:
            arcpy.management.AddField(
                fc, 
                self._field_name(field), 
                self._field_type(field), 
                field_length = self._field_length(field), 
                field_is_nullable = self._field_nullable(field))

        fields = [f.name for f in arcpy.ListFields(fc) if not f.name == arcpy.Describe(fc).OIDFieldName]
        arcpy.AddMessage(fields)

        select = f"SELECT"
        top = f"TOP {row_count}" if limit else ""
        from_table = f"* FROM {table_name}"

        with arcpy.da.InsertCursor(fc, fields) as IC:
            for row in arcsnow.cursor.execute(" ".join([select, top, from_table])):
                arcpy.AddMessage(row)
                IC.insertRow(row)
            

    def _field_type(self, field):
        if field[2] == 'TEXT' or field[2] == 'GEOGRAPHY':
            return 'TEXT'
        elif field[2] == 'NUMBER' and field[4] is not None:
            return 'DOUBLE'
        elif field[2] == "FLOAT":
            return 'FLOAT'
        elif field[2] == "BOOLEAN":
            return 'SHORT'
        else:
            return 'LONG'
            
    def _field_length(self, field):
        if field[2] == 'TEXT':
            return field[3]
        else:
            return 0
        
    def _field_name(self, field):
        return field[0]

    def _field_nullable(self, field):
        return 'NULLABLE' if field[1] == 'YES' else 'NON_NULLABLE'

            
class drop_table(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Drop Table"
        self.description = "Drop a table in Snowflake"
        self.canRunInBackground = False
        self.category = "General"
        
    def getParameterInfo(self):
        """Define parameter definitions"""
        table_name = arcpy.Parameter(
            displayName="Table Name",
            name="table_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        return [table_name]

    def execute(self, parameters, messages):
       if parameters[0].valueAsText:
            arcsnow = ArcSnow()
            arcsnow.login()

            table_name = parameters[0].valueAsText
            
            arcsnow.cursor.execute(f'DROP TABLE {table_name}')
            arcsnow.logout()

        
class cvs_upload(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Upload CSV"
        self.description = "Upload a CSV as a table to Snowflake"
        self.canRunInBackground = False
        self.category = "ETL"

    def _dtype_to_ftype(self, s):
        lookup = {
            "float":"DOUBLE",
            "float64":"DOUBLE",
            "int":"INT",
            "int64":"INT",
            "string":"VARCHAR",
            "object":"VARCHAR",
            "datetime":"DATETIME"            
        }

        return lookup[str(s)]

    def _fix_field_name(self, s):
        s = s.strip()
        
        for c in "()+~`-;:'><?/\\|\" ^":
            s = s.replace(c, "_")

        while "__" in s:
            s = s.replace("__", "_")

        if s[0] == "_":
            s = s[1:]

        if not s[0].isalpha():
            s = "t" + s

        if s[-1] == "_":
            s = s[:-1]
            
        return s

    def getParameterInfo(self):
        """Define parameter definitions"""
        input_csv_path = arcpy.Parameter(
            displayName="Input CSV",
            name="in_csv",
            datatype="DEFile",
            parameterType="Required",
            direction="Input")
        
        output_table_name = arcpy.Parameter(
            displayName="Table Name",
            name="table_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        
        field_definitions = arcpy.Parameter(
            displayName="Field Definitions",
            name="field_definition",
            datatype="GPValueTable",
            parameterType="Optional",
            direction="Input")


        field_definitions.columns = [
            ['GPString', 'Name'],
            ['GPString', 'Type'],
            ['GPLong', 'Length'],
            ['GPBoolean', 'Nullable']
        ]
        field_definitions.filters[1].type = 'ValueList'
        field_definitions.filters[1].list = ['VARCHAR', 'DOUBLE', 'INT', 'DATETIME']
        
        params = [input_csv_path, output_table_name, field_definitions]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated and parameters[0].valueAsText:
            parameters[1].value = os.path.splitext(os.path.basename(parameters[0].valueAsText))[0]
            
            df = pd.read_csv(parameters[0].valueAsText, engine='python', sep=',\s+', quoting=csv.QUOTE_ALL)
            fields = []
            for i in range(len(df.columns)):
                fields.append([
                    self._fix_field_name(df.columns[i]), # field name
                    self._dtype_to_ftype(df.dtypes[i]), # field type
                    255 if self._dtype_to_ftype(df.dtypes[i]) == "VARCHAR" else None, #field length
                    True, # nullable
                ])
            parameters[2].values = fields
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        if parameters[0].valueAsText:
            arcsnow = ArcSnow()
            arcsnow.login()

            table_name = parameters[1].valueAsText
            field_definitions = parameters[2].values
            field_names = [f[0] for f in field_definitions]
            arcsnow.cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
                            
            fields = []
            for field in field_definitions:
                field_name = field[0]
                field_type = field[1]
                if field_type == "VARCHAR":
                    field_type += f'({field[2]})'

                fields.append(f'{field_name} {field_type}')
                
            fields = ",".join(fields)

            create_table = f"CREATE TABLE {table_name} ({fields});"
            arcpy.AddMessage(create_table)

            arcsnow.cursor.execute(create_table)
            arcsnow.cursor.execute(f'GRANT ALL ON {table_name} TO ROLE ACCOUNTADMIN;')
            arcsnow.cursor.execute(f'GRANT SELECT ON {table_name} TO ROLE PUBLIC;')
            
            df = pd.read_csv(parameters[0].valueAsText, engine='python', sep=',\s+', quoting=csv.QUOTE_ALL)

            fields = ",".join(field_names)
            rows = []
            for index, row in df.iterrows():
                data = []
                for index, c_name in enumerate(df):
                    value = row[c_name]
                    if field_definitions[index][1] == "VARCHAR":
                        data.append(f"'{value}'")
                    else:
                        data.append(str(value))

                rows.append(",".join(data))

            values = ','.join([f'({x})' for x in rows])
            
            insert_values = f'INSERT INTO {table_name} ({fields}) VALUES {values};'
            
            arcpy.AddMessage(insert_values)

            arcsnow.cursor.execute(insert_values)
            arcsnow.logout()
            
        return


class ArcSnow(object):
    def __init__(self, path):
        self._credentials = Credentials(path)
        self._conn = None
        
    def login(self):
        self._conn = snowflake.connector.connect(
            user=self._credentials.username,
            password=self._credentials.rawpass,
            account=self._credentials.account,
            warehouse=self._credentials.warehouse,
            database=self._credentials.database,
            schema=self._credentials.schema
            )
        
        arcpy.AddMessage("Connection successful")
        
        self._conn.cursor().execute("USE ROLE ACCOUNTADMIN;")       
        self._conn.cursor().execute(f"USE WAREHOUSE {self._credentials.warehouse};")
        self._conn.cursor().execute(f"USE SCHEMA  {self._credentials.schema};")
        self._conn.cursor().execute(f"USE DATABASE {self._credentials.database}")
        
        arcpy.AddMessage("\n")
        arcpy.AddMessage("Current configuration")
        arcpy.AddMessage(f"  Role: ACCOUNTADMIN")
        arcpy.AddMessage(f"  Warehouse: {self._credentials.warehouse}")
        arcpy.AddMessage(f"  Database: {self._credentials.database}")
        arcpy.AddMessage(f"  Schema: {self._credentials.schema}")
    
    def logout(self):
        self._conn.cursor().close()
        self._conn.close()
        
    def schema(self, table_name):
        results = self._conn.cursor().execute("""SELECT COLUMN_NAME, IS_NULLABLE, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION \
        FROM INFORMATION_SCHEMA.COLUMNS\
        WHERE TABLE_NAME='{}'""".format(table_name))
        for r in results:
            print(r)
        
    @property
    def conn(self):
        return self._conn
    
    @property
    def cursor(self):
        return self._conn.cursor()


class Credentials(object):
    def __init__(self, path=None):
        self.__key_file = 'key.key'
        self.__key = ""
        self.__cred_file = "CredentialsFile.ini"
        self.location = "./"
        
        if path and self.__read_from_path(path):
            return
                
        #Stored within the Credential File
        self.username = ""
        self.__password = ""
        self.account = ""
        self.warehouse = ""
        self.database = ""
        self.schema = ""
        #File names and decyrption key


    @property
    def password(self):
        return self.__password

    @password.setter
    def password(self, password):
        self.__key = Fernet.generate_key()
        f = Fernet(self.__key)
        self.__password = f.encrypt(password.encode()).decode()
        del f
        
    @property
    def rawpass(self):
        f = Fernet(self.__key)
        decrypted = f.decrypt(self.__password.encode()).decode()
        del f
        
        return decrypted
        
    @property
    def path(self):
        return os.path.join(self.location, self.__cred_file)

    def create_cred(self):
        cred_filename = os.path.join(self.location, self.__cred_file)
        key_filename = os.path.join(self.location, self.__key_file)

        with open(cred_filename, 'w') as file_in:
            file_in.write(f"#Credential File:\nUsername={self.username}\nPassword={self.__password}\nAccount={self.account}\nWarehouse={self.warehouse}\nDatabase={self.database}\nSchema={self.schema}")

        if(os.path.exists(key_filename)):
            os.remove(key_filename)

        try:
            os_type = sys.platform
            with open(key_filename, 'w') as key_in:
                key_in.write(self.__key.decode())
                if(os_type == 'win32'):
                    ctypes.windll.kernel32.SetFileAttributesW(self.__key_file, 2)

        except PermissionError:
            os.remove(key_filename)
            arcpy.AddMessage("A Permission Error occurred.\n Please re run the script")

    def __read_from_path(self, path):
        try:
            cred_filename = path

            #The key file to decrypt password
            key_file = os.path.join(os.path.dirname(cred_filename), self.__key_file) 

            self.__key = ''
            with open(key_file, 'r') as key_in:
                    self.__key = key_in.read().encode()

            #Sets the value of decrpytion key    
            f = Fernet(self.__key)

            #Loops through each line of file to populate a dictionary from tuples in the form of key=value
            with open(cred_filename, 'r') as cred_in:
                lines = cred_in.readlines()
                config = {}
                for line in lines:
                    tuples = line.rstrip('\n').split('=',1)
                    if tuples[0] in ('Username', 'Password', 'Account', 'Warehouse', 'Database', 'Schema'):
                        config[tuples[0]] = tuples[1]

                #Password decryption
                passwd = f.decrypt(config['Password'].encode()).decode()
                config['Password'] = passwd
                
                self.username = config['Username']
                self.password = config['Password']
                self.account = config['Account']
                self.warehouse = config['Warehouse']
                self.database = config['Database']
                self.schema = config['Schema']
            return True
            
        except:
            return False
        