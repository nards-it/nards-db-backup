-- init_mysql.sql

-- Create a sample table
CREATE TABLE test_table (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

-- Insert some sample data
INSERT INTO test_table (name) VALUES ('Sample Data 1'), ('Sample Data 2');
