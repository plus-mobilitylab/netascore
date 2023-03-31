import psycopg2 as psy
import toolbox.helper as h
from jinjasql import JinjaSql
from typing import List
import re


class PostgresConnection:

    @staticmethod
    # creates a PostgresConnection object from settings object instead of individual params
    def from_settings_object(settings_object):
        return PostgresConnection(settings_object.dbname, settings_object.username, settings_object.password, 
                settings_object.host or None, settings_object.port or None, settings_object.on_existing)

    # constructor
    def __init__(self, dbname: str, user: str = "postgres", pw: str = "postgres", host: str = "localhost", port: int = 5432, on_existing: str = "abort"):
        self._dbname = dbname
        self._user = user
        self._pw = pw
        self._host = host
        self._port = port
        self._schema = "public"
        self._on_existing = on_existing
        
    _con = None
    _cur = None

    @property
    def port(self):
        return self._port

    @property
    def host(self):
        return self._host

    @property
    def user(self):
        return self._user
    
    @property
    def pw(self):
        return self._pw

    @property
    def dbname(self):
        return self._dbname

    # read-only connection string
    def get_connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.pw}@{self.host}:{str(self.port)}/{self.dbname}"
    connection_string: str = property(get_connection_string)

    def get_connection_string_old(self) -> str:
        if self.pw:
            return f"dbname='{self.dbname}' host='{self.host}' port='{str(self.port)}' user='{self.user}' password='{self.pw}'"
        else:
            return f"dbname='{self.dbname}' host='{self.host}' port='{str(self.port)}' user='{self.user}'"
    connection_string_old: str = property(get_connection_string_old)

    def connect(self):
        # skip if already connected
        if self._con:
            return
        # connect
        h.log(f"connecting to database '{self._dbname}' on {self._host}:{self._port}...")
        # create db connection
        try:
            self._con:psy.connection = psy.connect(dbname = self._dbname, host = self._host, port = self._port, user = self._user, password = self._pw,
                connect_timeout=3, keepalives=1, keepalives_idle=5, keepalives_interval=2, keepalives_count=2)       
        except psy.Error as e:
            h.log(f"ERROR while connecting to database: Error {e.pgcode} - {e.pgerror}")
            raise Exception("ERROR while connecting to database. Terminating.")
        # retreive cursor
        self._cur:psy.cursor = self._con.cursor()
    
    # define functions
    def ex(self, query, vars=None):
        if self._cur == None:
            self.connect()
        self._cur.execute(query, vars)
    
    def execute(self, query, vars=None):
        self.ex(query, vars)

    def commit(self):
        if self._cur == None:
            raise Exception("Called commit for non-existing database connection.")
        self._con.commit()

    def rollback(self):
        if self._cur == None:
            raise Exception("Called rollback for non-existing database connection.")
        self._con.rollback()
 
    # define getters

    def get_connection(self):
        return self._con

    con = property(get_connection)

    def get_cursor(self):
        return self._cur

    cur = property(get_cursor)

    # define extended setters and getters

    def set_working_schema(self, schema: str):
        print(f"setting working schema to: {schema}, public")
        self.ex(f"SET search_path = {schema}, public")
        self._schema = schema

    def get_working_schema(self)->str:
        return self._schema

    schema = property(get_working_schema, set_working_schema)

    # shorthand methods

    def query_one(self, *args):
        if len(args) > 1:
            self.ex(args[0], args[1])
        else:
            self.ex(args[0])
        return self.cur.fetchone()

    def query_all(self, *args):
        if len(args) > 1:
            self.ex(args[0], args[1])
        else:
            self.ex(args[0])
        return self.cur.fetchall()

    def close(self, commit_before_close=False):
        if self._con is not None:
            if commit_before_close:
                self._con.commit()
            self._con.close()
            print("DB connection closed.")
            self._con = None
            self._cur = None
        else:
            print("ERROR closing connection: no connection available.")

    # own methods

    def init_extensions_and_schema(self, schema):
        # create extensions
        h.log('create extensions')
        self.create_extension("postgis", "public")
        self.create_extension("postgis_raster", "public")
        self.create_extension("hstore", "public")

        # create schema
        h.log("create schema '{schema}' if not exists")
        self.create_schema(schema)

        # set search path
        h.log('set search path')
        self.schema = schema
        self.commit()


    # checks whether the given entity (e.g. table) exists within the database
    def exists(self, entity: str, schema: str = None) -> bool:
        if schema == None:
            schema = self.schema
        h.log(f"Checking whether entity exists: SELECT to_regclass('{schema + '.' + entity}');", h.LOG_LEVEL_4_DEBUG)
        result = self.query_one(f"SELECT to_regclass('{schema + '.' + entity}');")[0] != None
        h.log(f"...returned {result}")
        return result
    
    def use_if_exists(self, entity: str, schema: str = None) -> str:
        orig_entity = entity
        # try to extract schema from entity string if not specified
        if schema == None:
            spl = entity.split(".")
            if len(spl) > 1:
                entity = spl[1]
                schema = spl[0]
        if self.exists(entity, schema):
            return orig_entity
        return None

    def column_exists(self, column_name: str, schema: str, table: str) -> bool:
        if schema == None:
            schema = self.schema
        h.log(f"Checking whether column '{column_name}' exists in table '{schema}.{table}'", h.LOG_LEVEL_4_DEBUG)
        return self.query_one("""SELECT EXISTS (SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema=%s AND table_name=%s AND column_name=%s)""",
                              (schema, table, column_name))[0]

    def set_autocommit(self, autocommit: bool, pre_commit: bool = True):
        if autocommit:
            if pre_commit:
                self.con.commit()
            self._con.set_session(readonly=False, autocommit=True)
        else:
            self._con.set_session(readonly=False, autocommit=False)

    def vacuum(self, table, schema = None):
        # need to enable auto-commit for VACUUM command - not possible in transaction mode
        self.set_autocommit(True, pre_commit=True)
        if schema == None:
            self.ex("VACUUM FULL ANALYZE " + table)
        else:
            self.ex("VACUUM FULL ANALYZE " + schema + "." + table)
        # reset to manual commit again
        self.set_autocommit(False)

    def helper_replace_vacuum_statements(self, sql_string) -> str:
        return re.sub("vacuum full analyze", "ANALYZE", sql_string, flags=re.I)

    def geom_reproject(self, table, geomType, srid):
        h.log(f"reprojecting {geomType} geometry in table {table} to SRID {srid}", h.LOG_LEVEL_2_INFO)
        self.ex("""ALTER TABLE """ + table + """ 
            ALTER COLUMN geom 
            TYPE Geometry(%s, %s) 
            USING ST_Transform(geom, %s);""", (geomType, srid, srid))
        self.commit()

    def create_extension(self, extension: str, schema: str = None):
        h.log(f"creating extension: {extension}")
        if schema != None and len(schema) > 0:
            self.ex(f"CREATE EXTENSION IF NOT EXISTS {extension} WITH SCHEMA {schema};")
        else:
            self.ex(f"CREATE EXTENSION IF NOT EXISTS {extension};")

    def create_common_extensions(self):
        h.log("Setting up common DB extensions...", h.LOG_LEVEL_2_INFO)
        self.create_extension("postgis")
        self.create_extension("pgrouting")
        self.create_extension("hstore")

    def add_primary_key(self, table: str, columns: List[str], schema: str = None):
        h.log(f"Altering table {table} adding primary key")
        if schema is None:
            self.ex(f"ALTER TABLE {table} ADD PRIMARY KEY ({', '.join(columns)});")
        else:
            self.ex(f"ALTER TABLE {schema}.{table} ADD PRIMARY KEY ({', '.join(columns)});")

    def drop_table(self, table, cascade: bool = True, schema: str = None):
        casc = "CASCADE" if cascade else ""
        h.log(f"Dropping table {table} if exists {casc}")
        if schema == None:
            self.ex(f"DROP TABLE IF EXISTS {table} {casc};")
        else:
            self.ex(f"DROP TABLE IF EXISTS {schema}.{table} {casc};")

    def create_schema(self, schema: str):
        h.log(f"Creating schema {schema} if not exists")
        self.ex(f"CREATE SCHEMA IF NOT EXISTS {schema};")

    def drop_schema(self, schema, cascade: bool):
        casc = "CASCADE" if cascade else ""
        h.log(f"Dropping schema {schema} if exists {casc}")
        self.ex(f"DROP SCHEMA IF EXISTS {schema} {casc};")

    def verify_input_tables_exist(self, tables: List[str], schema: str = None):
        if schema == None:
            schema = self.schema
        for table in tables:
            if not self.exists(table, schema):
                raise Exception(
                    f"ERROR: at least one of the input tables does not exist. Please resolve issue and try again. Table: '{schema}.{table}'")
    
    def handle_conflicting_output_tables(self, tables: List[str], schema: str = None, on_existing:str = None)->bool:
        # returns True if tables were dropped or are not existing and process can continue normally, False if step should be skipped
        if on_existing is None:
            on_existing = self._on_existing
        t_exists:bool = False
        for table in tables:
            if self.exists(table, schema):
                t_exists = True
        if not t_exists:
            return True # no conflicts -> all good
        if on_existing == "skip":
            return False # return False, calling code needs to handle skipping of step
        if on_existing == "delete":
            for table in tables:
                if self.exists(table, schema):
                    self.drop_table(table, cascade=True, schema = schema)
            self.commit()
            return True
        # case "abort" / in general: throw Error
        raise Exception("Output table(s) already exist. Please resolve conflict manually or specify 'on_existing' parameter to delete or skip existing tables.")

    def execute_sql_from_file(self, script_file_name, subdir:str="sql/"):
        if not subdir.endswith("/") or subdir.endswith("\\"):
            subdir+="/"
        h.log(f"Executing SQL from file: '{subdir}{script_file_name}.sql'")
        # load sql template
        with open(f"{subdir}{script_file_name}.sql", "r") as sqlfile:
            sql = sqlfile.read()
        self.ex(sql)

    def execute_sql_template_string(self, template: str, parameters: dict, override_parameters: dict = None) -> None:
        '''
        Apply a JinjaSql template (string) substituting parameters (dict) and execute
        the final SQL. If override_parameters is given, parameters with the same key
        name will be replaced by the values from override_parameters
        Make sure to use "<param_name> | sqlsafe" for table or schema names in the template - otherwise they get String-quoted which leads to an error.
        '''

        # if override_parameters are given, check whether given keys exist in params and replace them accordingly
        template_params = h.overrideParams(parameters, override_parameters)

        j = JinjaSql(param_style='pyformat')
        query, bind_params = j.prepare_query(template, template_params)
        h.log("query: " + str(query), h.LOG_LEVEL_4_DEBUG)
        #dbg_file = open("debug_sql.sql", "w")
        #n = dbg_file.write(query)
        #dbg_file.close()
        h.log("bind params: " + str(bind_params), h.LOG_LEVEL_4_DEBUG)
        self.ex(query, bind_params)
        # TODO: error handling and reporting

    def execute_template_sql_from_file(self, template_file_name: str, parameters: dict, override_parameters: dict = None,
                             autocommit: bool = True, template_subdir="sql/templates/") -> None:
        h.log(f"Loading SQL template from '{template_subdir}{template_file_name}.sql.j2'...")
        with open(f"{template_subdir}{template_file_name}.sql.j2", "r") as sqlfile:
            sql = sqlfile.read()
        # current workaround for vacuum full analyze not working in multiple-statement SQL string: replace with ANALYZE
        # see issue on Gitlab for further info
        sql = self.helper_replace_vacuum_statements(sql) # TODO: remove in future
        # execute SQL
        h.log("Executing SQL statements...")
        if autocommit:
            self.set_autocommit(True, pre_commit=True) # set autocommit TRUE, so VACUUM can take place in SQL
        self.execute_sql_template_string(sql, parameters, override_parameters)
        if autocommit:
            self.set_autocommit(False) # reset to manual commit mode