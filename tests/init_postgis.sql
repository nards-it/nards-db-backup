-- init_postgis.sql

-- Create a sample table
CREATE TABLE test_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

-- Insert some sample data
INSERT INTO test_table (name) VALUES ('Sample Data 1'), ('Sample Data 2');
